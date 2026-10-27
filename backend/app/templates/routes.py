"""The templates API: templates, their drafts and published versions, and their images.

Everything here is for those who build templates (BUILD_TEMPLATES: Administrators
and Report Designers). Drafts save whatever their problems, so a designer can stop
halfway; a save over someone else's newer one is refused (409) rather than lost.
Publishing needs a draft without problems, freezes it as the next version and logs
its SHA-256. Saves while someone works are logged once every few minutes per
person; everything else is logged as it happens.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.dependencies import DB, client_ip, require
from app.auth.sessions import UserSession
from app.roles import Capability
from app.templates.assets import AssetRejected, clean_asset
from app.templates.changes import Changes, changes
from app.templates.checks import Problem, check
from app.templates.content import (
    MAX_CONTENT_BYTES,
    SCHEMA_VERSION,
    TemplateContent,
    starter_content,
)
from app.templates.models import Template, TemplateAsset, TemplateVersion
from app.users import User

router = APIRouter(prefix="/templates")

Designer = Annotated[UserSession, Depends(require(Capability.BUILD_TEMPLATES))]

NOT_FOUND = "That template doesn't exist."
# Saves while someone works on a draft are logged at most this often per person.
LOG_SAVES_EVERY = timedelta(minutes=10)


def _stripped(value: str | None) -> str | None:
    return None if value is None else value.strip()


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)

    _strip = field_validator("name", "description")(_stripped)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)

    _strip = field_validator("name", "description")(_stripped)


class DraftSummary(BaseModel):
    revision: int
    saved_at: datetime
    saved_by: str | None


class VersionSummary(BaseModel):
    number: int
    published_at: datetime
    published_by: str | None
    note: str
    content_sha256: str


class AssetOut(BaseModel):
    sha256: str
    name: str
    content_type: str
    width: int
    height: int
    url: str


class TemplateSummary(BaseModel):
    id: int
    uuid: str
    name: str
    description: str
    latest_version: int | None
    published_at: datetime | None
    draft: DraftSummary | None
    retired: bool
    updated_at: datetime


class TemplateDetail(TemplateSummary):
    versions: list[VersionSummary]
    assets: list[AssetOut]


class ProblemOut(BaseModel):
    element: str
    field: str
    message: str


class DraftOut(DraftSummary):
    content: dict[str, Any]
    problems: list[ProblemOut]


class DraftIn(BaseModel):
    content: dict[str, Any]
    # The revision the editor started from: a save over a newer one is refused.
    revision: int


class Saved(BaseModel):
    revision: int
    saved_at: datetime
    problems: list[ProblemOut]


class NewDraft(BaseModel):
    # The published version to start from; the newest when not given.
    from_version: int | None = None


class PublishIn(BaseModel):
    revision: int
    note: str = Field(default="", max_length=500)


class VersionOut(VersionSummary):
    content: dict[str, Any]


class CopyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    _strip = field_validator("name")(_stripped)


# Helpers


def _log(db: Session, request: Request, record: UserSession, action: str, template_id: int,
         details: dict[str, object] | None = None) -> None:
    audit.append(db, action, actor_id=record.user.id, actor_name=record.user.username,
                 target_type="template", target_id=str(template_id), ip=client_ip(request),
                 details=details)


def canonical(content: TemplateContent) -> str:
    """The stored form: sorted keys and no spaces, so equal content hashes the same."""
    return json.dumps(content.dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse_content(raw: dict[str, Any]) -> TemplateContent:
    """The content as submitted, checked for structure; 422 with where it went wrong."""
    if len(json.dumps(raw, separators=(",", ":"))) > MAX_CONTENT_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "The template is larger than 2 MB.")
    try:
        return TemplateContent.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        message = re.sub(r"^Value error, ", "", first["msg"])
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"The template isn't valid at {where}: {message}") from None


def _names(db: Session, user_ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in user_ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(wanted)))
    return {user_id: name for user_id, name in rows}


def _template(db: Session, template_id: int) -> Template:
    template = db.get(Template, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return template


def _draft(db: Session, template_id: int) -> TemplateVersion | None:
    return db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template_id,
                                                   TemplateVersion.number.is_(None)))


def _published(db: Session, template_id: int) -> list[TemplateVersion]:
    return list(db.scalars(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id, TemplateVersion.number.is_not(None))
        .order_by(TemplateVersion.number.desc())
    ))


def _assets(db: Session, template_id: int) -> list[TemplateAsset]:
    return list(db.scalars(select(TemplateAsset).where(TemplateAsset.template_id == template_id)
                           .order_by(TemplateAsset.id)))


def _asset_out(asset: TemplateAsset) -> AssetOut:
    return AssetOut(sha256=asset.sha256, name=asset.name, content_type=asset.content_type,
                    width=asset.width, height=asset.height,
                    url=f"/api/templates/{asset.template_id}/assets/{asset.sha256}")


def _problems(db: Session, template_id: int, content: TemplateContent) -> list[Problem]:
    assets = set(db.scalars(select(TemplateAsset.sha256)
                            .where(TemplateAsset.template_id == template_id)))
    return check(content, assets=assets)


def _problems_out(problems: list[Problem]) -> list[ProblemOut]:
    return [ProblemOut(element=p.element, field=p.field, message=p.message) for p in problems]


def _summary(db: Session, template: Template, names: dict[int, str]) -> dict[str, Any]:
    draft = _draft(db, template.id)
    latest = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template.id,
                                                     TemplateVersion.number.is_not(None))
                       .order_by(TemplateVersion.number.desc()).limit(1))
    return {
        "id": template.id, "uuid": template.uuid, "name": template.name,
        "description": template.description,
        "latest_version": latest.number if latest else None,
        "published_at": latest.published_at if latest else None,
        "draft": DraftSummary(revision=draft.revision, saved_at=draft.saved_at,
                              saved_by=names.get(draft.saved_by or 0)) if draft else None,
        "retired": template.retired_at is not None,
        "updated_at": template.updated_at,
    }


def _detail(db: Session, template: Template) -> TemplateDetail:
    versions = _published(db, template.id)
    draft = _draft(db, template.id)
    names = _names(db, {v.published_by for v in versions} | {draft.saved_by if draft else None})
    return TemplateDetail(
        **_summary(db, template, names),
        versions=[VersionSummary(number=v.number or 0, published_at=v.published_at or v.saved_at,
                                 published_by=names.get(v.published_by or 0), note=v.note,
                                 content_sha256=v.content_sha256) for v in versions],
        assets=[_asset_out(a) for a in _assets(db, template.id)],
    )


def _new_version(template_id: int, content: TemplateContent, user_id: int) -> TemplateVersion:
    stored = canonical(content)
    return TemplateVersion(template_id=template_id, number=None, content=stored,
                           content_sha256=sha256(stored), schema_version=SCHEMA_VERSION,
                           revision=1, saved_at=clock.utcnow(), saved_by=user_id, note="")


def _draft_out(db: Session, template_id: int, draft: TemplateVersion) -> DraftOut:
    content = TemplateContent.model_validate_json(draft.content)
    return DraftOut(revision=draft.revision, saved_at=draft.saved_at,
                    saved_by=_names(db, {draft.saved_by}).get(draft.saved_by or 0),
                    content=content.dump(),
                    problems=_problems_out(_problems(db, template_id, content)))


def _touch(template: Template, record: UserSession) -> None:
    template.updated_at = clock.utcnow()
    template.updated_by = record.user_id


def _conflict(db: Session, draft: TemplateVersion) -> HTTPException:
    who = _names(db, {draft.saved_by}).get(draft.saved_by or 0, "someone")
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"{who} saved this template at {draft.saved_at:%H:%M} UTC, after you opened it. "
        "Reload it to see their changes.",
    )


# Templates


@router.get("")
def list_templates(record: Designer, db: DB) -> list[TemplateSummary]:
    templates = list(db.scalars(select(Template)))
    drafts = list(db.scalars(select(TemplateVersion).where(TemplateVersion.number.is_(None))))
    names = _names(db, {d.saved_by for d in drafts})
    found = [TemplateSummary(**_summary(db, t, names)) for t in templates]
    return sorted(found, key=lambda t: (t.retired, t.name.casefold()))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, request: Request, record: Designer, db: DB
                    ) -> TemplateDetail:
    now = clock.utcnow()
    template = Template(uuid=str(uuid.uuid4()), name=body.name, description=body.description,
                        created_at=now, created_by=record.user_id, updated_at=now,
                        updated_by=record.user_id)
    db.add(template)
    db.flush()
    db.add(_new_version(template.id, starter_content(), record.user_id))
    _log(db, request, record, "template.created", template.id, {"name": template.name})
    db.commit()
    return _detail(db, template)


@router.get("/{template_id}")
def get_template(template_id: int, record: Designer, db: DB) -> TemplateDetail:
    return _detail(db, _template(db, template_id))


@router.patch("/{template_id}")
def update_template(template_id: int, body: TemplateUpdate, request: Request, record: Designer,
                    db: DB) -> TemplateDetail:
    template = _template(db, template_id)
    changed = []
    if body.name is not None and body.name != template.name:
        template.name = body.name
        changed.append("name")
    if body.description is not None and body.description != template.description:
        template.description = body.description
        changed.append("description")
    if changed:
        _touch(template, record)
        _log(db, request, record, "template.changed", template.id,
             {"changed": changed, "name": template.name})
        db.commit()
    return _detail(db, template)


@router.post("/{template_id}/retire")
def retire_template(template_id: int, request: Request, record: Designer, db: DB
                    ) -> TemplateDetail:
    template = _template(db, template_id)
    if template.retired_at is None:
        template.retired_at = clock.utcnow()
        template.retired_by = record.user_id
        _log(db, request, record, "template.retired", template.id)
        db.commit()
    return _detail(db, template)


@router.post("/{template_id}/restore")
def restore_template(template_id: int, request: Request, record: Designer, db: DB
                     ) -> TemplateDetail:
    template = _template(db, template_id)
    if template.retired_at is not None:
        template.retired_at = template.retired_by = None
        _log(db, request, record, "template.restored", template.id)
        db.commit()
    return _detail(db, template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, request: Request, record: Designer, db: DB) -> Response:
    template = _template(db, template_id)
    if _published(db, template.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "A published template is kept: retire it instead.")
    db.delete(template)
    _log(db, request, record, "template.deleted", template_id, {"name": template.name})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{template_id}/copy", status_code=status.HTTP_201_CREATED)
def copy_template(template_id: int, body: CopyIn, request: Request, record: Designer, db: DB
                  ) -> TemplateDetail:
    """A new template starting from this one's draft, or its newest version: for a
    translation, or a variant."""
    source = _template(db, template_id)
    start = _draft(db, source.id) or next(iter(_published(db, source.id)), None)
    if start is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That template has nothing to copy.")
    now = clock.utcnow()
    copy = Template(uuid=str(uuid.uuid4()), name=body.name, description=source.description,
                    created_at=now, created_by=record.user_id, updated_at=now,
                    updated_by=record.user_id)
    db.add(copy)
    db.flush()
    db.add(_new_version(copy.id, TemplateContent.model_validate_json(start.content),
                        record.user_id))
    for asset in _assets(db, source.id):
        db.add(TemplateAsset(template_id=copy.id, sha256=asset.sha256, name=asset.name,
                             content_type=asset.content_type, width=asset.width,
                             height=asset.height, data=asset.data, created_at=now,
                             created_by=record.user_id))
    _log(db, request, record, "template.copied", copy.id,
         {"from": source.id, "name": copy.name})
    db.commit()
    return _detail(db, copy)


# The draft


@router.get("/{template_id}/draft")
def get_draft(template_id: int, record: Designer, db: DB) -> DraftOut:
    template = _template(db, template_id)
    draft = _draft(db, template.id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "There's no draft: start one from the newest version.")
    return _draft_out(db, template.id, draft)


@router.post("/{template_id}/draft", status_code=status.HTTP_201_CREATED)
def start_draft(template_id: int, request: Request, record: Designer, db: DB,
                body: Annotated[NewDraft | None, Body()] = None) -> DraftOut:
    template = _template(db, template_id)
    if _draft(db, template.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This template has a draft already.")
    versions = _published(db, template.id)
    wanted = body.from_version if body else None
    start = next((v for v in versions if wanted is None or v.number == wanted), None)
    if start is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That version doesn't exist.")
    draft = _new_version(template.id, TemplateContent.model_validate_json(start.content),
                         record.user_id)
    db.add(draft)
    _touch(template, record)
    _log(db, request, record, "template.draft_started", template.id, {"from_version": start.number})
    db.commit()
    return _draft_out(db, template.id, draft)


@router.put("/{template_id}/draft")
def save_draft(template_id: int, body: DraftIn, request: Request, record: Designer, db: DB
               ) -> Saved:
    template = _template(db, template_id)
    draft = _draft(db, template.id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "There's no draft: start one from the newest version.")
    content = parse_content(body.content)
    if body.revision != draft.revision:
        raise _conflict(db, draft)
    stored = canonical(content)
    now = clock.utcnow()
    if stored != draft.content:
        draft.content = stored
        draft.content_sha256 = sha256(stored)
        draft.revision += 1
        draft.saved_at = now
        draft.saved_by = record.user_id
        _touch(template, record)
        if (draft.logged_by != record.user_id or draft.logged_at is None
                or now - draft.logged_at >= LOG_SAVES_EVERY):
            _log(db, request, record, "template.draft_saved", template.id,
                 {"revision": draft.revision})
            draft.logged_at, draft.logged_by = now, record.user_id
        db.commit()
    return Saved(revision=draft.revision, saved_at=draft.saved_at,
                 problems=_problems_out(_problems(db, template.id, content)))


@router.delete("/{template_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def discard_draft(template_id: int, request: Request, record: Designer, db: DB) -> Response:
    template = _template(db, template_id)
    draft = _draft(db, template.id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no draft to discard.")
    if not _published(db, template.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This template was never published: delete it instead.")
    db.delete(draft)
    _touch(template, record)
    _log(db, request, record, "template.draft_discarded", template.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{template_id}/publish")
def publish(template_id: int, body: PublishIn, request: Request, record: Designer, db: DB
            ) -> VersionSummary:
    template = _template(db, template_id)
    draft = _draft(db, template.id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no draft to publish.")
    if body.revision != draft.revision:
        raise _conflict(db, draft)
    problems = _problems(db, template.id, TemplateContent.model_validate_json(draft.content))
    if problems:
        count = len(problems)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Fix the {count} problem{'s' if count != 1 else ''} first: a template with "
            "problems can't be published.",
        )
    number = (db.scalar(select(func.max(TemplateVersion.number))
                        .where(TemplateVersion.template_id == template.id)) or 0) + 1
    now = clock.utcnow()
    draft.number = number
    draft.published_at = now
    draft.published_by = record.user_id
    draft.note = body.note.strip()
    _touch(template, record)
    _log(db, request, record, "template.published", template.id,
         {"version": number, "sha256": draft.content_sha256})
    db.commit()
    return VersionSummary(number=number, published_at=now, published_by=record.user.display_name,
                          note=draft.note, content_sha256=draft.content_sha256)


# Versions


def _version(db: Session, template_id: int, number: int) -> TemplateVersion:
    version = db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template_id,
                                                      TemplateVersion.number == number))
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That version doesn't exist.")
    return version


@router.get("/{template_id}/versions/{number}")
def get_version(template_id: int, number: int, record: Designer, db: DB) -> VersionOut:
    _template(db, template_id)
    version = _version(db, template_id, number)
    return VersionOut(
        number=number, published_at=version.published_at or version.saved_at,
        published_by=_names(db, {version.published_by}).get(version.published_by or 0),
        note=version.note, content_sha256=version.content_sha256,
        content=TemplateContent.model_validate_json(version.content).dump(),
    )


@router.get("/{template_id}/changes")
def get_changes(template_id: int, record: Designer, db: DB,
                since: Annotated[int | None, Query()] = None,
                to: Annotated[int | None, Query()] = None) -> Changes:
    """What changed from one version (the newest by default) to another (the draft by
    default)."""
    _template(db, template_id)
    if to is None:
        draft = _draft(db, template_id)
        if draft is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no draft.")
        new = draft
    else:
        new = _version(db, template_id, to)
    if since is None:
        latest = next(iter(_published(db, template_id)), None)
        old = TemplateContent.model_validate_json(latest.content) if latest else None
    else:
        old = TemplateContent.model_validate_json(_version(db, template_id, since).content)
    return changes(old, TemplateContent.model_validate_json(new.content))


# Images


@router.post("/{template_id}/assets", status_code=status.HTTP_201_CREATED)
def upload_asset(
    template_id: int, data: Annotated[bytes, Body(media_type="application/octet-stream")],
    request: Request, record: Designer, db: DB,
    name: Annotated[str, Query(min_length=1, max_length=200)] = "image",
) -> AssetOut:
    template = _template(db, template_id)
    try:
        clean = clean_asset(data)
    except AssetRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    existing = db.scalar(select(TemplateAsset).where(TemplateAsset.template_id == template.id,
                                                     TemplateAsset.sha256 == clean.sha256))
    if existing is not None:
        return _asset_out(existing)
    safe_name = re.sub(r"[^\w .()-]", "_", name).strip() or "image"
    asset = TemplateAsset(template_id=template.id, sha256=clean.sha256, name=safe_name[:200],
                          content_type=clean.content_type, width=clean.width,
                          height=clean.height, data=clean.data, created_at=clock.utcnow(),
                          created_by=record.user_id)
    db.add(asset)
    _touch(template, record)
    _log(db, request, record, "template.image_added", template.id,
         {"sha256": clean.sha256, "type": clean.content_type})
    db.commit()
    return _asset_out(asset)


@router.get("/{template_id}/assets/{digest}")
def get_asset(template_id: int, digest: str, record: Designer, db: DB) -> Response:
    asset = db.scalar(select(TemplateAsset).where(TemplateAsset.template_id == template_id,
                                                  TemplateAsset.sha256 == digest))
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That image doesn't exist.")
    return Response(asset.data, media_type=asset.content_type, headers={
        # Named by its hash, so it never changes; and never run as a page.
        "Cache-Control": "private, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    })
