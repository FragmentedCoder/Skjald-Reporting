"""Customers' report backgrounds: the letterhead art reports print on.

A customer can have one background: an A4 PDF (the usual case, often a letterhead
saved from Word), or a PNG, JPEG or SVG picture of an A4 page. A PDF's first page is
used behind a report's first page and its second, if it has one, behind the rest. A
PDF is converted to SVG by the renderer (app/renderer.py), which has no network:
the worker hands it the file through the folder they share and waits for the pages,
holding no database lock meanwhile. Every page is then cleaned like any other SVG
(app/svg.py). The original and the pages are sealed with the customer's key, so
deleting the customer leaves nothing readable behind. Margins keep a report's text
clear of the art. A customer without a background gets plain pages.
"""

from __future__ import annotations

import base64
import io
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Float, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import jobs
from app.customers import Customer, Keyring
from app.db import Base, UTCDateTime
from app.renderer import EXCHANGE, RenderError
from app.svg import SvgRejected, clean_svg

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PAGE_BYTES = 12 * 1024 * 1024
A4_RATIO = 297 / 210
WAIT_FOR_RENDERER = 90


class BackgroundRejected(ValueError):
    """The upload can't be a background; the message is fit to show."""


class CustomerBackground(Base):
    __tablename__ = "customer_backgrounds"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    # {"file": base64, "type": media type}, sealed with the customer's key.
    sealed_original: Mapped[bytes] = mapped_column(LargeBinary)
    # {"pages": [svg, ...]}, sealed with the customer's key, once converted.
    sealed_pages: Mapped[bytes | None] = mapped_column(LargeBinary)
    # converting, ready or failed
    status: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(String(300), default="")
    # How far a report's text keeps from the page's edges, in millimetres.
    margin_top: Mapped[float] = mapped_column(Float, default=30)
    margin_bottom: Mapped[float] = mapped_column(Float, default=25)
    margin_left: Mapped[float] = mapped_column(Float, default=20)
    margin_right: Mapped[float] = mapped_column(Float, default=20)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


def _page_from_picture(raw: bytes) -> str:
    """A PNG or JPEG of an A4 page as an SVG page holding it, re-encoded without metadata."""
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.format not in ("PNG", "JPEG"):
                raise BackgroundRejected("Use an A4 PDF, or a PNG, JPEG or SVG picture of a page.")
            opened.load()
            picture = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise BackgroundRejected("That file isn't a picture Skjald can use.") from exc
    if abs(picture.height / picture.width - A4_RATIO) > 0.03:
        raise BackgroundRejected("The picture must have an A4 page's proportions (210 × 297).")
    picture.thumbnail((2480, 3508))
    out = io.BytesIO()
    picture.save(out, format="PNG", optimize=True)
    data = base64.b64encode(out.getvalue()).decode()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 297"><image '
            f'href="data:image/png;base64,{data}" width="210" height="297" '
            f'preserveAspectRatio="none"/></svg>')


def kind_of(raw: bytes) -> str:
    head = raw[:1024].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.lower().startswith((b"<?xml", b"<svg", b"<!--")):
        return "image/svg+xml"
    return "image/raster"


def prepare(raw: bytes) -> tuple[str, list[str] | None]:
    """The upload's type, and its page if it needs no converting (a picture)."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise BackgroundRejected("The file is larger than 10 MB.")
    kind = kind_of(raw)
    if kind == "application/pdf":
        return kind, None
    if kind == "image/svg+xml":
        try:
            svg = clean_svg(raw, MAX_PAGE_BYTES)
        except SvgRejected as exc:
            raise BackgroundRejected(str(exc)) from exc
        if abs(svg.height / svg.width - A4_RATIO) > 0.03:
            raise BackgroundRejected("The picture must have an A4 page's proportions (210 × 297).")
        return kind, [svg.data.decode()]
    return "image/png", [_page_from_picture(raw)]


def render_pdf(pdf: bytes, exchange: Path = EXCHANGE, wait: float = WAIT_FOR_RENDERER) -> list[str]:
    """The renderer's SVG pages for a PDF, through the folder the two share."""
    job = uuid.uuid4().hex
    (exchange / "in").mkdir(parents=True, exist_ok=True)
    partial = exchange / "in" / f"{job}.part"
    partial.write_bytes(pdf)
    partial.rename(exchange / "in" / f"{job}.pdf")
    result_file = exchange / "out" / f"{job}.json"
    deadline = time.monotonic() + wait
    try:
        while not result_file.exists():
            if time.monotonic() > deadline:
                raise RenderError("Skjald couldn't convert the file just now. Upload it again "
                                  "in a few minutes.")
            time.sleep(0.2)
        result: dict[str, Any] = json.loads(result_file.read_text())
    finally:
        (exchange / "in" / f"{job}.pdf").unlink(missing_ok=True)
        result_file.unlink(missing_ok=True)
    if "error" in result:
        raise RenderError(str(result["error"]))
    return [str(page) for page in result["pages"]]


@jobs.handles("background.convert")
def convert(db: Session, job: jobs.Job) -> dict[str, Any]:
    customer_id = int(job.data()["customer_id"])
    row = db.get(CustomerBackground, customer_id)
    customer = db.get(Customer, customer_id)
    if row is None or customer is None or row.status != "converting":
        return {"skipped": True}
    sealer = Keyring().sealer(customer)
    original = sealer.open("background", customer_id, row.sealed_original)
    uploaded_at = row.uploaded_at
    db.commit()  # long work follows: hold no lock meanwhile
    try:
        pages = [clean_svg(page.encode(), MAX_PAGE_BYTES).data.decode()
                 for page in render_pdf(base64.b64decode(original["file"]))]
        status, message = "ready", ""
    except (RenderError, SvgRejected) as exc:
        pages, status, message = [], "failed", str(exc)
    row = db.get(CustomerBackground, customer_id)
    if row is None or row.uploaded_at != uploaded_at:
        return {"skipped": "replaced"}
    row.sealed_pages = (sealer.seal("background-pages", customer_id, {"pages": pages})
                        if pages else None)
    row.status, row.message = status, message
    return {"status": status, "pages": len(pages)}
