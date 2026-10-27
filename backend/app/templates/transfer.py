"""Moving templates between installs: export a version as a .skjald file, import one as
a new template's draft (app/templates/files.py has the format and its checks).

For those who build templates (BUILD_TEMPLATES). An export carries the shared library
entries the template reads and the company's default style; an import adds those
that aren't here yet and never changes ones that are. Exports and imports are logged.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth.dependencies import DB, effective_capabilities
from app.auth.sessions import UserSession
from app.backgrounds import MAX_PAGE_BYTES
from app.library.models import LibraryEntry, LibraryVersion
from app.library.routes import current_entries
from app.library.values import parse_value
from app.roles import Capability
from app.styles import artwork
from app.styles.content import StyleContent, assets
from app.styles.models import Style, StyleAsset, StyleVersion
from app.svg import SvgRejected, clean_svg
from app.templates import files
from app.templates.assets import AssetRejected, CleanAsset, clean_asset
from app.templates.content import TemplateContent
from app.templates.models import Template, TemplateAsset, TemplateVersion
from app.templates.routes import (
    Designer,
    TemplateDetail,
    _assets,
    _detail,
    _draft,
    _log,
    _new_version,
    _published,
    _template,
    _version,
    canonical,
    parse_content,
)
from app.version import skjald_version

router = APIRouter(prefix="/templates")

# Library entries a template reads: vars.<key>, text.<key> and lookup("<key>", …), as
# they appear in its canonical JSON (where quotes inside strings are escaped).
_LIBRARY = re.compile(r"\b(vars|text)\.([a-z][a-z0-9_]*)|lookup\(\s*\\?[\"']([a-z][a-z0-9_]*)")
_KINDS = {"vars": "variable", "text": "snippet"}


class ImportOut(BaseModel):
    template: TemplateDetail
    library_added: list[str]
    library_kept: list[str]
    style_added: str | None
    style_kept: str | None


def _library_used(db: Session, content: TemplateContent) -> list[dict[str, Any]]:
    wanted: set[tuple[str, str]] = set()
    for match in _LIBRARY.finditer(canonical(content)):
        if match.group(3):
            wanted.add(("table", match.group(3)))
        else:
            wanted.add((_KINDS[match.group(1)], match.group(2)))
    return [{"kind": entry.kind, "key": entry.key, "description": entry.description,
             "value": json.loads(version.value)}
            for entry, version in current_entries(db) if (entry.kind, entry.key) in wanted]


def _company_style(db: Session) -> tuple[dict[str, Any] | None, list[files.Picture]]:
    style = db.scalar(select(Style).where(Style.customer_id.is_(None), Style.is_default.is_(True),
                                          Style.removed_at.is_(None)))
    if style is None:
        return None, []
    version = db.scalar(select(StyleVersion).where(StyleVersion.style_id == style.id,
                                                   StyleVersion.number == style.current))
    assert version is not None and version.content is not None
    content = StyleContent.model_validate_json(version.content)
    used = assets(content)
    pictures = [files.Picture(a.sha256, a.content_type, a.data) for a in db.scalars(
        select(StyleAsset).where(StyleAsset.style_id == style.id)) if a.sha256 in used]
    return {"name": style.name, "content": content.model_dump(mode="json")}, pictures


def _filename(name: str, number: int | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "template"
    return f"{slug}-{f'v{number}' if number else 'draft'}.skjald"


@router.get("/{template_id}/export")
def export_template(template_id: int, request: Request, record: Designer, db: DB,
                    version: Annotated[int | None, Query(ge=1)] = None) -> Response:
    """A published version (the newest by default) or, with no version yet, the draft."""
    template = _template(db, template_id)
    row: TemplateVersion | None = (
        _version(db, template.id, version) if version is not None
        else next(iter(_published(db, template.id)), None) or _draft(db, template.id))
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That template has nothing to export.")
    content = TemplateContent.model_validate_json(row.content)
    style, style_pictures = _company_style(db)
    data = files.write(files.Export(
        uuid=template.uuid, name=template.name, description=template.description,
        version=row.number, content=content,
        pictures=[files.Picture(a.sha256, a.content_type, a.data)
                  for a in _assets(db, template.id) if a.content_type in files.EXTENSIONS],
        library=_library_used(db, content), style=style, style_pictures=style_pictures,
        app_version=skjald_version(), exported_at=clock.utcnow().isoformat(timespec="seconds"),
    ))
    _log(db, request, record, "template.exported", template.id,
         {"version": row.number, "bytes": len(data)})
    db.commit()
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{_filename(template.name, row.number)}"',
        "Cache-Control": "no-store",
    })


def _clean_pictures(pictures: dict[str, bytes], svg_bytes: int | None = None
                    ) -> tuple[dict[str, str], dict[str, CleanAsset]]:
    """Each picture re-encoded (or rebuilt, for SVG): the old hashes' new ones, and the
    cleaned pictures by their new hash. svg_bytes allows larger SVGs (style artwork)."""
    renamed: dict[str, str] = {}
    cleaned: dict[str, CleanAsset] = {}
    for old, body in pictures.items():
        try:
            if svg_bytes and body.lstrip(b"\xef\xbb\xbf \t\r\n")[:5].lower() in (
                    b"<?xml", b"<svg ", b"<svg>", b"<!--"):
                svg = clean_svg(body, svg_bytes)
                clean = CleanAsset(svg.data, "image/svg+xml", svg.width, svg.height)
            else:
                clean = clean_asset(body)
        except (AssetRejected, SvgRejected) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"An image in the file can't be used: {exc}") from None
        renamed[old] = clean.sha256
        cleaned[clean.sha256] = clean
    return renamed, cleaned


def _renamed(raw: Any, renamed: dict[str, str]) -> Any:
    text = json.dumps(raw)
    for old, new in renamed.items():
        text = text.replace(old, new)
    return json.loads(text)


def _import_library(db: Session, record: UserSession, entries: list[dict[str, Any]]
                    ) -> tuple[list[str], list[str]]:
    added, kept = [], []
    now = clock.utcnow()
    for item in entries[:200]:
        kind, key = item.get("kind"), item.get("key")
        if kind not in ("variable", "snippet", "table") or not isinstance(key, str) or \
                not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", key):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "library.json holds an entry Skjald can't read.")
        name = {"variable": f"vars.{key}", "snippet": f"text.{key}"}.get(kind, f'lookup("{key}")')
        if db.scalar(select(LibraryEntry.id).where(LibraryEntry.kind == kind,
                                                   LibraryEntry.key == key)) is not None:
            kept.append(name)
            continue
        try:
            value = parse_value(kind, item.get("value"))
        except (ValueError, ValidationError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"The library entry {name} in the file isn't valid.") from None
        entry = LibraryEntry(kind=kind, key=key, current=1, created_at=now,
                             created_by=record.user_id,
                             description=str(item.get("description") or "")[:500])
        db.add(entry)
        db.flush()
        db.add(LibraryVersion(entry_id=entry.id, number=1, saved_at=now, saved_by=record.user_id,
                              value=json.dumps(value, ensure_ascii=False, sort_keys=True)))
        added.append(name)
    return added, kept


def _import_style(db: Session, record: UserSession, style: dict[str, Any] | None,
                  pictures: dict[str, bytes]) -> tuple[str | None, str | None]:
    if style is None:
        return None, None
    name = str(style.get("name") or "Imported style").strip()[:100] or "Imported style"
    taken = [s.name for s in db.scalars(select(Style).where(Style.customer_id.is_(None),
                                                             Style.removed_at.is_(None)))]
    if any((n or "").casefold() == name.casefold() for n in taken):
        return None, name
    renamed, cleaned = _clean_pictures(pictures, MAX_PAGE_BYTES)
    try:
        content = StyleContent.model_validate(_renamed(style.get("content") or {}, renamed))
    except ValidationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The style in the file isn't valid.") from None
    now = clock.utcnow()
    made = Style(name=name, is_default=False, current=1, created_at=now, created_by=record.user_id)
    db.add(made)
    db.flush()
    for clean in cleaned.values():
        artwork.store(db, made, clean.data, clean.content_type, clean.width, clean.height,
                      record.user_id)
    if assets(content) - set(cleaned):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The style in the file uses a picture the file doesn't have.")
    db.add(StyleVersion(style_id=made.id, number=1, saved_at=now, saved_by=record.user_id,
                        content=json.dumps(content.model_dump(mode="json"))))
    return name, None


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_template(data: Annotated[bytes, Body(media_type="application/octet-stream")],
                    request: Request, record: Designer, db: DB) -> ImportOut:
    try:
        imported = files.read(data)
    except files.TemplateFileRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    renamed, cleaned = _clean_pictures(imported.pictures)
    content = parse_content(_renamed(imported.content, renamed))
    now = clock.utcnow()
    try:
        kept_uuid = str(uuid.UUID(imported.uuid))
    except ValueError:
        kept_uuid = ""
    if not kept_uuid or db.scalar(select(Template.id).where(Template.uuid == kept_uuid)):
        kept_uuid = str(uuid.uuid4())
    names = {t.casefold() for t in db.scalars(select(Template.name))}
    name = imported.name.strip()[:180] or "Imported template"
    if name.casefold() in names:
        name = f"{name} (imported)"
    template = Template(uuid=kept_uuid, name=name, description=imported.description[:1000],
                        created_at=now, created_by=record.user_id, updated_at=now,
                        updated_by=record.user_id)
    db.add(template)
    db.flush()
    db.add(_new_version(template.id, content, record.user_id))
    for sha, clean in cleaned.items():
        db.add(TemplateAsset(template_id=template.id, sha256=sha, name="image",
                             content_type=clean.content_type, width=clean.width,
                             height=clean.height, data=clean.data, created_at=now,
                             created_by=record.user_id))
    added, kept = _import_library(db, record, imported.library)
    style_added = style_kept = None
    if Capability.EDIT_STYLES in effective_capabilities(db, record, request):
        style_added, style_kept = _import_style(db, record, imported.style,
                                                imported.style_pictures)
    _log(db, request, record, "template.imported", template.id, {
        "name": name, "from_uuid": imported.uuid or None, "library_added": added,
        "style_added": style_added})
    db.commit()
    return ImportOut(template=_detail(db, template), library_added=added, library_kept=kept,
                     style_added=style_added, style_kept=style_kept)

