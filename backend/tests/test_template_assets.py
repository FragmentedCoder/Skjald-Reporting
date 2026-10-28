"""Images uploaded with templates: re-encoded, or rebuilt from an allowlist (SVG)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.svg import SvgRejected, clean_svg
from app.templates.assets import AssetRejected, clean_asset

SVG_HEAD = b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '


def test_svg_keeps_drawing_and_drops_everything_that_could_act() -> None:
    raw = SVG_HEAD + b'''viewBox="0 0 640 150" onload="alert(1)">
      <script>alert(1)</script>
      <style>@import url(https://evil.example/x.css);</style>
      <defs><linearGradient id="g"><stop offset="0" stop-color="#0F1B2D"/></linearGradient></defs>
      <rect width="10" height="10" fill="url(#g)" onclick="steal()"/>
      <rect width="10" height="10" fill="url(https://evil.example/x)" style="fill:red"/>
      <a xlink:href="javascript:alert(1)"><text x="1" y="2">Firewall &amp; portal</text></a>
      <text x="5" y="5">Kept <tspan>here</tspan> too</text>
      <foreignObject><div xmlns="http://www.w3.org/1999/xhtml">html</div></foreignObject>
      <image href="https://evil.example/tracker.png" width="1" height="1"/>
      <image xlink:href="data:image/png;base64,iVBORw0KGgo=" width="1" height="1"/>
      <use href="#g"/><use href="https://evil.example/s.svg#x"/>
      <animate attributeName="href" to="javascript:alert(1)"/>
    </svg>'''
    clean = clean_svg(raw)
    text = clean.data.decode()
    assert (clean.width, clean.height) == (640, 150)
    for gone in ("script", "style", "onload", "onclick", "evil.example", "foreignObject",
                 "javascript", "animate", "<a", "@import"):
        assert gone not in text
    for kept in ('fill="url(#g)"', "<linearGradient", "Kept <tspan>here</tspan> too",
                 'href="data:image/png;base64,iVBORw0KGgo="', '<use href="#g"'):
        assert kept in text
    assert "Firewall" not in text  # inside a link, which is dropped with what it holds
    # Cleaning what was cleaned changes nothing.
    assert clean_svg(clean.data).data == clean.data


@pytest.mark.parametrize("raw", [
    b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;">]>'
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><text>&b;</text></svg>',
    b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><text>&x;</text></svg>',
    b'<html><body>not a picture</body></html>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>',
    b"<svg",
])
def test_svg_refuses_entities_and_non_pictures(raw: bytes) -> None:
    with pytest.raises(SvgRejected):
        clean_svg(raw)


def test_images_are_re_encoded_without_their_metadata() -> None:
    photo = io.BytesIO()
    exif = Image.Exif()
    exif[0x8825] = {2: (55.0, 40.0, 0.0)}  # GPS latitude
    Image.new("RGB", (3000, 1500), "#2B5D8A").save(photo, format="JPEG", exif=exif.tobytes())
    clean = clean_asset(photo.getvalue())
    assert clean.content_type == "image/jpeg"
    assert (clean.width, clean.height) == (2480, 1240)
    with Image.open(io.BytesIO(clean.data)) as reopened:
        assert not reopened.getexif()
    with pytest.raises(AssetRejected, match="PNG, JPEG or SVG"):
        gif = io.BytesIO()
        Image.new("RGB", (2, 2)).save(gif, format="GIF")
        clean_asset(gif.getvalue())
    with pytest.raises(AssetRejected):
        clean_asset(b"MZ\x90\x00 an executable")
