"""Images uploaded with a template: diagrams, logos, pictures for its layout.

PNG and JPEG files are decoded and re-encoded with Pillow, which drops metadata
(location included) and anything hidden in the file, and scales them to fit the
largest a page can show sharply. SVG files are rebuilt from an allowlist
(app/svg.py). Each is stored by the SHA-256 of what's kept.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.svg import SvgRejected, clean_svg

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
# A full A4 width at 300 dots per inch.
MAX_SIZE = (2480, 2480)


class AssetRejected(ValueError):
    """The upload isn't an image Skjald will keep; the message is fit to show."""


@dataclass(frozen=True)
class CleanAsset:
    data: bytes
    content_type: str
    width: int
    height: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _looks_like_svg(raw: bytes) -> bool:
    head = raw[:1024].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return head.startswith((b"<?xml", b"<svg", b"<!--"))


def clean_asset(raw: bytes) -> CleanAsset:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise AssetRejected("The image is larger than 4 MB.")
    if _looks_like_svg(raw):
        try:
            svg = clean_svg(raw)
        except SvgRejected as exc:
            raise AssetRejected(str(exc)) from exc
        return CleanAsset(svg.data, "image/svg+xml", svg.width, svg.height)
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.format not in ("PNG", "JPEG"):
                raise AssetRejected("Use a PNG, JPEG or SVG image.")
            photo = opened.format == "JPEG"
            opened.load()
            image = ImageOps.exif_transpose(opened)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise AssetRejected("That file isn't an image Skjald can use.") from exc
    image.thumbnail(MAX_SIZE)
    out = io.BytesIO()
    if photo:
        image.convert("RGB").save(out, format="JPEG", quality=90, optimize=True)
    else:
        image.convert("RGBA").save(out, format="PNG", optimize=True)
    return CleanAsset(out.getvalue(), "image/jpeg" if photo else "image/png",
                      image.width, image.height)
