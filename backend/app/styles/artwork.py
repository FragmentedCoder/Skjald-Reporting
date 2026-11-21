"""A style's pictures: artwork drawn behind its pages, and images placed on them.

Artwork is an A4 PDF (a letterhead, often saved from Word) or a PNG, JPEG or SVG
picture of a page, taken as a customer's report background is (app/backgrounds.py):
a PDF goes to the renderer, which has no network, and comes back as SVG pages. An
image for a page design is a PNG, JPEG or SVG of any shape, re-encoded or rebuilt
from an allowlist (app/templates/assets.py). Each picture is kept by its SHA-256 and
never changed; a customer style's are sealed with the customer's key.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, jobs
from app.backgrounds import MAX_PAGE_BYTES, BackgroundRejected, convert_pdf, prepare
from app.customers import Customer, Keyring
from app.styles.models import Style, StyleAsset, StyleUpload
from app.svg import clean_svg
from app.templates.assets import AssetRejected, clean_asset


@dataclass
class Accepted:
    """An upload's outcome: its pages, or the conversion it waits for."""

    status: str
    pages: list[str] = field(default_factory=list)
    upload: int | None = None


def _sealer(db: Session, style: Style, keyring: Keyring | None = None) -> Any:
    if style.customer_id is None:
        return None
    customer = db.get(Customer, style.customer_id)
    assert customer is not None
    return (keyring or Keyring()).sealer(customer)


def store(db: Session, style: Style, data: bytes, content_type: str, width: int, height: int,
          user_id: int | None) -> str:
    """Keep a picture for the style, once however often it's uploaded; its SHA-256."""
    sha = hashlib.sha256(data).hexdigest()
    if db.scalar(select(StyleAsset.id).where(StyleAsset.style_id == style.id,
                                             StyleAsset.sha256 == sha)) is None:
        sealer = _sealer(db, style)
        kept = (sealer.seal(f"style-asset/{sha}", style.id,
                            {"data": base64.b64encode(data).decode()}) if sealer else data)
        db.add(StyleAsset(style_id=style.id, sha256=sha, content_type=content_type, data=kept,
                          width=width, height=height, created_at=clock.utcnow(),
                          created_by=user_id))
        db.flush()
    return sha


def load(db: Session, style: Style, sha: str, keyring: Keyring | None = None
         ) -> tuple[bytes, str] | None:
    """A picture of the style's and its type."""
    asset = db.scalar(select(StyleAsset).where(StyleAsset.style_id == style.id,
                                               StyleAsset.sha256 == sha))
    if asset is None:
        return None
    sealer = _sealer(db, style, keyring)
    data = (base64.b64decode(sealer.open(f"style-asset/{sha}", style.id, asset.data)["data"])
            if sealer else asset.data)
    return data, asset.content_type


def _store_page(db: Session, style: Style, svg: str, user_id: int | None) -> str:
    clean = clean_svg(svg.encode(), MAX_PAGE_BYTES)
    return store(db, style, clean.data, "image/svg+xml", clean.width, clean.height, user_id)


def accept_artwork(db: Session, style: Style, raw: bytes, user_id: int | None) -> Accepted:
    """Artwork for the style's pages: ready now, or once the renderer converts the PDF."""
    kind, pages = prepare(raw)
    if pages is not None:
        return Accepted("ready", [_store_page(db, style, page, user_id) for page in pages])
    upload = StyleUpload(style_id=style.id, original=b"", status="converting", message="",
                         pages="[]", created_at=clock.utcnow(), created_by=user_id)
    db.add(upload)
    db.flush()
    sealer = _sealer(db, style)
    upload.original = (sealer.seal("style-upload", upload.id,
                                   {"file": base64.b64encode(raw).decode()})
                       if sealer else raw)
    jobs.enqueue(db, "style.artwork", {"upload_id": upload.id}, requested_by=user_id)
    return Accepted("converting", upload=upload.id)


def accept_image(db: Session, style: Style, raw: bytes, user_id: int | None) -> str:
    """An image for a page design; AssetRejected says why one can't be used."""
    clean = clean_asset(raw)
    return store(db, style, clean.data, clean.content_type, clean.width, clean.height, user_id)


def upload_pages(upload: StyleUpload) -> list[str]:
    pages: list[str] = json.loads(upload.pages)
    return pages


@jobs.handles("style.artwork")
def convert(db: Session, job: jobs.Job) -> dict[str, Any]:
    upload = db.get(StyleUpload, int(job.data()["upload_id"]))
    style = db.get(Style, upload.style_id) if upload else None
    if upload is None or style is None or upload.status != "converting":
        return {"skipped": True}
    sealer = _sealer(db, style)
    pdf = (base64.b64decode(sealer.open("style-upload", upload.id, upload.original)["file"])
           if sealer else upload.original)
    upload_id = upload.id
    db.commit()  # long work follows: hold no lock meanwhile
    try:
        svgs = convert_pdf(pdf)
        status, message = "ready", ""
    except BackgroundRejected as exc:
        svgs, status, message = [], "failed", str(exc)
    upload = db.get(StyleUpload, upload_id)
    style = db.get(Style, upload.style_id) if upload else None
    if upload is None or style is None:
        return {"skipped": "removed"}
    pages = [_store_page(db, style, svg, upload.created_by) for svg in svgs]
    upload.status, upload.message, upload.pages = status, message, json.dumps(pages)
    upload.original = b""
    return {"status": status, "pages": len(pages)}


__all__ = ["Accepted", "AssetRejected", "BackgroundRejected", "accept_artwork", "accept_image",
           "load", "store", "upload_pages"]
