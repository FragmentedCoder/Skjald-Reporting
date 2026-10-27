"""The report styles API: company and customer styles, their pictures, and the styles
each customer's reports use.

Administrators and Report Designers make and change styles (EDIT_STYLES); whoever
builds templates or runs customers may read them, to preview a template in a style
or choose a customer's. A customer style belongs to its customer: only people who
see that customer's name see it (404 otherwise), and its name, versions and pictures
are sealed with the customer's key. Every save is a new version, refused if it was
made from an older one than the newest (409). Changes are written to the audit log
by style ID and version; names and content stay out of it.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.dependencies import DB, FullSession, client_ip, effective_capabilities, require
from app.auth.sessions import UserSession
from app.background_routes import Styler
from app.branding import company_timezone
from app.customer_routes import visible_customer
from app.customers import Customer, Keyring, visibility
from app.library.routes import current_entries
from app.library.values import library_names
from app.roles import Capability, roles_of
from app.styles import artwork
from app.styles.content import StyleContent, assets, problems
from app.styles.models import CustomerStyles, Style, StyleAsset, StyleUpload, StyleVersion
from app.users import User

router = APIRouter(prefix="/styles")
customer_router = APIRouter(prefix="/customers/{customer_id}/report-style")

Editor = Annotated[UserSession, Depends(require(Capability.EDIT_STYLES))]
READERS = {Capability.EDIT_STYLES, Capability.BUILD_TEMPLATES, Capability.MANAGE_CUSTOMERS}

NOT_FOUND = "That style doesn't exist."


def reader(request: Request, record: FullSession, db: DB) -> UserSession:
    """Someone who may look at report styles."""
    if not effective_capabilities(db, record, request) & READERS:
        audit.append(db, "auth.access_denied", actor_id=record.user.id,
                     actor_name=record.user.username, ip=client_ip(request),
                     details={"capability": "edit_styles", "path": request.url.path})
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't see report styles.")
    return record


Reader = Annotated[UserSession, Depends(reader)]


class StyleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # None: a company style.
    customer_id: int | None = None
    # A customer style's company style; None: the Skjald default.
    based_on: int | None = None


class StyleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    based_on: int | None = None
    content: StyleContent
    # The version the change was made from: a change over a newer one is refused.
    version: int


class DefaultIn(BaseModel):
    # None: the Skjald default.
    style_id: int | None


class AssetOut(BaseModel):
    sha256: str
    content_type: str
    width: int
    height: int


class StyleSummary(BaseModel):
    id: int
    name: str
    customer_id: int | None
    customer_name: str | None
    based_on: int | None
    is_default: bool
    version: int
    updated_at: datetime
    updated_by: str | None


class StyleOut(StyleSummary):
    content: StyleContent
    # The styles this one stacks on, bottom first, above the Skjald default.
    below: list[StyleContent]
    assets: list[AssetOut]
    problems: list[str]


class VersionOut(BaseModel):
    number: int
    saved_at: datetime
    saved_by: str | None


class UploadOut(BaseModel):
    status: Literal["ready", "converting", "failed"]
    message: str = ""
    # The pages' SHA-256s: one, or two for a PDF with a page for the rest.
    pages: list[str] = []
    upload: int | None = None


class CustomerStylesIn(BaseModel):
    # None: the company's default style.
    default_style_id: int | None
    allowed: list[int] = Field(default_factory=list, max_length=50)


class CustomerStylesOut(CustomerStylesIn):
    # The styles this customer's reports can use: the company's and its own.
    choices: list[StyleSummary]
    company_default: int | None


# Reading styles


class Opened:
    """One request's view of styles: names and contents, opened once each."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.keyring = Keyring()
        self._users: dict[int, str | None] = {}

    def sealer(self, style: Style) -> Any:
        if style.customer_id is None:
            return None
        customer = self.db.get(Customer, style.customer_id)
        assert customer is not None
        return self.keyring.sealer(customer)

    def name(self, style: Style) -> str:
        sealer = self.sealer(style)
        if sealer is None:
            return style.name or ""
        assert style.sealed_name is not None
        return str(sealer.open("style-name", style.id, style.sealed_name)["name"])

    def version(self, style: Style, number: int | None = None) -> StyleVersion:
        found = self.db.scalar(select(StyleVersion).where(
            StyleVersion.style_id == style.id,
            StyleVersion.number == (number if number is not None else style.current)))
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "That version doesn't exist.")
        return found

    def content(self, style: Style, version: StyleVersion) -> StyleContent:
        sealer = self.sealer(style)
        if sealer is None:
            assert version.content is not None
            return StyleContent.model_validate_json(version.content)
        assert version.sealed_content is not None
        return StyleContent.model_validate(
            sealer.open(f"style-version/{version.number}", style.id, version.sealed_content))

    def below(self, style: Style) -> list[StyleContent]:
        base = self.db.get(Style, style.based_on) if style.based_on else None
        if base is None or base.removed_at is not None:
            return []
        return [self.content(base, self.version(base))]

    def user(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        if user_id not in self._users:
            found = self.db.get(User, user_id)
            self._users[user_id] = found.display_name if found else None
        return self._users[user_id]

    def summary(self, style: Style) -> StyleSummary:
        latest = self.version(style)
        customer = self.db.get(Customer, style.customer_id) if style.customer_id else None
        return StyleSummary(
            id=style.id, name=self.name(style), customer_id=style.customer_id,
            customer_name=self.keyring.name(customer) if customer else None,
            based_on=style.based_on, is_default=style.is_default, version=style.current,
            updated_at=latest.saved_at, updated_by=self.user(latest.saved_by),
        )


def _sees_customer(db: Session, record: UserSession, customer_id: int) -> bool:
    return visibility(db, record.user_id, roles_of(db, record.user_id), customer_id) is not None


def _style(db: Session, request: Request, record: UserSession, style_id: int) -> Style:
    style = db.get(Style, style_id)
    if style is None or style.removed_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if style.customer_id is not None:
        visible_customer(db, request, record, style.customer_id, need="names")
    return style


def _company_style(db: Session, style_id: int | None) -> Style | None:
    if style_id is None:
        return None
    base = db.get(Style, style_id)
    if base is None or base.removed_at is not None or base.customer_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "A customer style stacks on one of the company's styles.")
    return base


def _log(db: Session, request: Request, record: UserSession, action: str, style: Style,
         **details: object) -> None:
    if style.customer_id is not None:
        details["customer_id"] = style.customer_id
    audit.append(db, action, actor_id=record.user.id, actor_name=record.user.username,
                 target_type="style", target_id=str(style.id), ip=client_ip(request),
                 details=details or None)


def _problems(db: Session, content: StyleContent) -> list[str]:
    library = library_names(entry for entry, _ in current_entries(db))
    return problems(content, timezone=company_timezone(db), library=library)


def _out(opened: Opened, style: Style) -> StyleOut:
    content = opened.content(style, opened.version(style))
    kept = opened.db.scalars(select(StyleAsset).where(StyleAsset.style_id == style.id)
                             .order_by(StyleAsset.id))
    return StyleOut(
        **opened.summary(style).model_dump(), content=content, below=opened.below(style),
        assets=[AssetOut(sha256=a.sha256, content_type=a.content_type, width=a.width,
                         height=a.height) for a in kept],
        problems=_problems(opened.db, content),
    )


def _taken(opened: Opened, name: str, customer_id: int | None, but: int | None = None) -> bool:
    rivals = opened.db.scalars(select(Style).where(
        Style.removed_at.is_(None), Style.id != (but or 0),
        Style.customer_id.is_(None) if customer_id is None else Style.customer_id == customer_id))
    return any(opened.name(s).casefold() == name.strip().casefold() for s in rivals)


def _new_version(opened: Opened, style: Style, content: StyleContent, user_id: int,
                 number: int) -> None:
    sealer = opened.sealer(style)
    raw = content.model_dump(mode="json")
    opened.db.add(StyleVersion(
        style_id=style.id, number=number,
        content=None if sealer else json.dumps(raw),
        sealed_content=sealer.seal(f"style-version/{number}", style.id, raw) if sealer else None,
        saved_at=clock.utcnow(), saved_by=user_id,
    ))


@router.get("")
def list_styles(record: Reader, db: DB) -> list[StyleSummary]:
    """The company's styles, then the customer styles of customers this person sees."""
    opened = Opened(db)
    styles = db.scalars(select(Style).where(Style.removed_at.is_(None)).order_by(Style.id))
    seen: dict[int, bool] = {}
    found = []
    for style in styles:
        if style.customer_id is not None:
            if style.customer_id not in seen:
                seen[style.customer_id] = _sees_customer(db, record, style.customer_id)
            if not seen[style.customer_id]:
                continue
        found.append(opened.summary(style))
    return sorted(found, key=lambda s: (s.customer_id is not None, s.customer_name or "",
                                        s.name.casefold()))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_style(body: StyleIn, request: Request, record: Editor, db: DB) -> StyleOut:
    if body.customer_id is not None:
        visible_customer(db, request, record, body.customer_id, need="names")
    elif body.based_on is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "A company style stacks on the Skjald default.")
    _company_style(db, body.based_on)
    opened = Opened(db)
    if _taken(opened, body.name, body.customer_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A style with that name exists.")
    style = Style(customer_id=body.customer_id, based_on=body.based_on, is_default=False,
                  current=1, created_at=clock.utcnow(), created_by=record.user_id)
    if body.customer_id is None:
        style.name = body.name.strip()
    db.add(style)
    db.flush()
    sealer = opened.sealer(style)
    if sealer:
        style.sealed_name = sealer.seal("style-name", style.id, {"name": body.name.strip()})
    _new_version(opened, style, StyleContent(), record.user_id, 1)
    _log(db, request, record, "style.created", style)
    db.commit()
    return _out(opened, style)


@router.put("/company-default")
def set_company_default(body: DefaultIn, request: Request, record: Editor, db: DB
                        ) -> list[StyleSummary]:
    """Which company style reports use unless a customer's choice says otherwise."""
    chosen = _company_style(db, body.style_id)
    for style in db.scalars(select(Style).where(Style.is_default.is_(True))):
        style.is_default = False
    if chosen is not None:
        chosen.is_default = True
    audit.append(db, "style.default_changed", actor_id=record.user.id,
                 actor_name=record.user.username, target_type="style",
                 target_id=str(chosen.id) if chosen else None, ip=client_ip(request))
    db.commit()
    return list_styles(record, db)


@router.get("/{style_id}")
def get_style(style_id: int, request: Request, record: Reader, db: DB) -> StyleOut:
    return _out(Opened(db), _style(db, request, record, style_id))


@router.put("/{style_id}")
def update_style(style_id: int, body: StyleUpdate, request: Request, record: Editor, db: DB
                 ) -> StyleOut:
    style = _style(db, request, record, style_id)
    if body.version != style.current:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Someone saved this style since you opened it. Reload to see "
                            "their changes.")
    if style.customer_id is None and body.based_on is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "A company style stacks on the Skjald default.")
    _company_style(db, body.based_on)
    opened = Opened(db)
    if _taken(opened, body.name, style.customer_id, but=style.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A style with that name exists.")
    kept = set(db.scalars(select(StyleAsset.sha256).where(StyleAsset.style_id == style.id)))
    if assets(body.content) - kept:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The style uses a picture it doesn't have. Upload it again.")
    found = _problems(db, body.content)
    if found:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, " ".join(found))
    sealer = opened.sealer(style)
    if sealer:
        style.sealed_name = sealer.seal("style-name", style.id, {"name": body.name.strip()})
    else:
        style.name = body.name.strip()
    style.based_on = body.based_on
    style.current += 1
    _new_version(opened, style, body.content, record.user_id, style.current)
    db.flush()
    _log(db, request, record, "style.changed", style, version=style.current)
    db.commit()
    return _out(opened, style)


@router.delete("/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_style(style_id: int, request: Request, record: Editor, db: DB) -> Response:
    """Mark the style removed: its versions stay, and customers' choices skip it."""
    style = _style(db, request, record, style_id)
    style.removed_at, style.removed_by = clock.utcnow(), record.user_id
    style.is_default = False
    _log(db, request, record, "style.removed", style)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{style_id}/versions")
def list_versions(style_id: int, request: Request, record: Reader, db: DB) -> list[VersionOut]:
    style = _style(db, request, record, style_id)
    opened = Opened(db)
    return [VersionOut(number=v.number, saved_at=v.saved_at, saved_by=opened.user(v.saved_by))
            for v in db.scalars(select(StyleVersion).where(StyleVersion.style_id == style.id)
                                .order_by(StyleVersion.number.desc()))]


@router.get("/{style_id}/versions/{number}")
def get_version(style_id: int, number: int, request: Request, record: Reader, db: DB
                ) -> StyleContent:
    style = _style(db, request, record, style_id)
    opened = Opened(db)
    return opened.content(style, opened.version(style, number))


@router.post("/{style_id}/assets")
def upload_asset(
    style_id: int, data: Annotated[bytes, Body(media_type="application/octet-stream")],
    request: Request, record: Editor, db: DB,
    use: Annotated[Literal["artwork", "image"], Query()] = "image",
) -> UploadOut:
    """Artwork for the pages (an A4 PDF or picture), or an image for a page design."""
    style = _style(db, request, record, style_id)
    try:
        if use == "artwork":
            accepted = artwork.accept_artwork(db, style, data, record.user_id)
        else:
            accepted = artwork.Accepted("ready", [artwork.accept_image(db, style, data,
                                                                       record.user_id)])
    except (artwork.BackgroundRejected, artwork.AssetRejected) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _log(db, request, record, "style.picture_added", style, use=use, pages=accepted.pages,
         upload=accepted.upload)
    db.commit()
    return UploadOut(status=accepted.status, pages=accepted.pages,  # type: ignore[arg-type]
                     upload=accepted.upload)


@router.get("/{style_id}/uploads/{upload_id}")
def get_upload(style_id: int, upload_id: int, request: Request, record: Editor, db: DB
               ) -> UploadOut:
    style = _style(db, request, record, style_id)
    upload = db.get(StyleUpload, upload_id)
    if upload is None or upload.style_id != style.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That upload doesn't exist.")
    return UploadOut(status=upload.status, message=upload.message,  # type: ignore[arg-type]
                     pages=artwork.upload_pages(upload), upload=upload.id)


@router.get("/{style_id}/assets/{sha256}")
def get_asset(style_id: int, sha256: str, request: Request, record: Reader, db: DB) -> Response:
    style = _style(db, request, record, style_id)
    found = artwork.load(db, style, sha256)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That picture doesn't exist.")
    data, content_type = found
    return Response(data, media_type=content_type, headers={
        # Kept by its hash and never changed; a customer's stays out of shared caches.
        "Cache-Control": ("private, max-age=31536000, immutable" if style.customer_id
                          else "max-age=31536000, immutable"),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy":
            "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox",
    })


# The styles a customer's reports use


def _customer_choices(opened: Opened, customer_id: int) -> list[Style]:
    return list(opened.db.scalars(select(Style).where(
        Style.removed_at.is_(None),
        (Style.customer_id.is_(None)) | (Style.customer_id == customer_id)).order_by(Style.id)))


def _customer_styles_out(opened: Opened, customer_id: int) -> CustomerStylesOut:
    choices = _customer_choices(opened, customer_id)
    ids = {s.id for s in choices}
    row = opened.db.get(CustomerStyles, customer_id)
    default = row.default_style_id if row and row.default_style_id in ids else None
    allowed = [i for i in json.loads(row.allowed) if i in ids] if row else []
    return CustomerStylesOut(
        default_style_id=default, allowed=allowed,
        choices=[opened.summary(s) for s in choices],
        company_default=next((s.id for s in choices if s.is_default), None),
    )


@customer_router.get("")
def get_customer_styles(customer_id: int, request: Request, record: Reader, db: DB
                        ) -> CustomerStylesOut:
    customer, _ = visible_customer(db, request, record, customer_id, need="names")
    return _customer_styles_out(Opened(db), customer.id)


@customer_router.put("")
def set_customer_styles(customer_id: int, body: CustomerStylesIn, request: Request,
                        record: Styler, db: DB) -> CustomerStylesOut:
    customer, _ = visible_customer(db, request, record, customer_id, need="names")
    opened = Opened(db)
    ids = {s.id for s in _customer_choices(opened, customer.id)}
    chosen = set(body.allowed) | ({body.default_style_id} if body.default_style_id else set())
    if chosen - ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Choose among the company's styles and this customer's own.")
    row = db.get(CustomerStyles, customer.id)
    if row is None:
        row = CustomerStyles(customer_id=customer.id, allowed="[]")
        db.add(row)
    row.default_style_id = body.default_style_id
    row.allowed = json.dumps(sorted(set(body.allowed) - {body.default_style_id or 0}))
    audit.append(db, "customer.report_style_changed", actor_id=record.user.id,
                 actor_name=record.user.username, target_type="customer",
                 target_id=str(customer.id), ip=client_ip(request),
                 details={"default": body.default_style_id, "allowed": json.loads(row.allowed)})
    db.commit()
    return _customer_styles_out(opened, customer.id)
