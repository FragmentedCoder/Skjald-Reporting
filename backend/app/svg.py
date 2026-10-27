"""SVG pictures, cleaned before Skjald stores them.

An SVG is a document, and can carry scripts, links to other sites, styles that load
things and entities that blow up when expanded. So the file is parsed with
defusedxml (no DTDs, so no entities) and rebuilt from an allowlist: shapes, paths,
text, gradients, clipping and masks, with their drawing attributes. Everything
else is dropped, including script, style, foreignObject, animation and links. The
only references kept are to the picture's own parts (#id) and embedded PNG or JPEG
data. The cleaned file is what gets stored and printed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
MAX_BYTES = 2 * 1024 * 1024
MAX_ELEMENTS = 20_000
MAX_DEPTH = 50

ELEMENTS = frozenset({
    "svg", "g", "defs", "title", "desc", "symbol", "use", "path", "rect", "circle", "ellipse",
    "line", "polyline", "polygon", "text", "tspan", "linearGradient", "radialGradient", "stop",
    "clipPath", "mask", "pattern", "image",
})
ATTRIBUTES = frozenset({
    "id", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy", "width",
    "height", "d", "points", "transform", "viewBox", "preserveAspectRatio", "version", "fill",
    "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity",
    "visibility", "display", "font-family", "font-size", "font-weight", "font-style",
    "text-anchor", "dominant-baseline", "letter-spacing", "word-spacing", "dx", "dy", "rotate",
    "offset", "stop-color", "stop-opacity", "gradientUnits", "gradientTransform",
    "spreadMethod", "clip-path", "clip-rule", "clipPathUnits", "mask", "maskUnits",
    "maskContentUnits", "patternUnits", "patternContentUnits", "patternTransform",
    "color", "href",
})
# The only url() a value may hold: a reference to the picture's own part.
_URL = re.compile(r"url\(\s*([^)]*)\s*\)", re.IGNORECASE)
_LOCAL = re.compile(r"^#[A-Za-z_][\w.\-]*$")
_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg);base64,[A-Za-z0-9+/=\s]+$")
_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$")


class SvgRejected(ValueError):
    """The file isn't an SVG Skjald will store; the message is fit to show."""


@dataclass(frozen=True)
class CleanSvg:
    data: bytes
    width: int
    height: int


def _value_ok(name: str, value: str) -> bool:
    lowered = value.lower()
    if "javascript:" in lowered or "expression(" in lowered or "@import" in lowered:
        return False
    if name == "href":
        return bool(_LOCAL.match(value) or _DATA_IMAGE.match(value))
    return all(_LOCAL.match(ref.strip("'\" ")) for ref in _URL.findall(value))


def _clean(element: ET.Element, depth: int, count: list[int]) -> ET.Element | None:
    tag = element.tag
    if not isinstance(tag, str) or not tag.startswith("{" + SVG + "}"):
        return None
    local = tag[len(SVG) + 2:]
    if local not in ELEMENTS:
        return None
    count[0] += 1
    if count[0] > MAX_ELEMENTS or depth > MAX_DEPTH:
        raise SvgRejected("The SVG is too complex to use.")
    clean = ET.Element(local)
    for name, value in element.attrib.items():
        plain = name
        if name.startswith("{" + XLINK + "}"):
            plain = name[len(XLINK) + 2:]
            if plain != "href":
                continue
        elif name.startswith("{"):
            continue
        if plain in ATTRIBUTES and _value_ok(plain, value):
            clean.set(plain, value)
    if local == "image" and "href" not in clean.attrib:
        return None
    if local == "use" and not _LOCAL.match(clean.get("href", "")):
        return None
    clean.text = element.text if local in ("text", "tspan", "title", "desc") else None
    for child in element:
        cleaned = _clean(child, depth + 1, count)
        if cleaned is not None:
            cleaned.tail = child.tail if local in ("text", "tspan") else None
            clean.append(cleaned)
    return clean


def _size(root: ET.Element) -> tuple[int, int]:
    view_box = root.get("viewBox", "").replace(",", " ").split()
    if len(view_box) == 4:
        try:
            width, height = float(view_box[2]), float(view_box[3])
            if width > 0 and height > 0:
                return max(1, round(width)), max(1, round(height))
        except ValueError:
            pass
    sizes = [_LENGTH.match(root.get(name, "")) for name in ("width", "height")]
    if sizes[0] and sizes[1]:
        return max(1, round(float(sizes[0].group(1)))), max(1, round(float(sizes[1].group(1))))
    raise SvgRejected("The SVG needs a viewBox, or a width and height, so it can be sized.")


def clean_svg(raw: bytes) -> CleanSvg:
    if len(raw) > MAX_BYTES:
        raise SvgRejected("The SVG is larger than 2 MB.")
    try:
        root = fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ET.ParseError, ValueError) as exc:
        raise SvgRejected("That file isn't an SVG Skjald can read.") from exc
    if root.tag != "{" + SVG + "}svg":
        raise SvgRejected("That file isn't an SVG picture.")
    cleaned = _clean(root, 1, [0])
    assert cleaned is not None
    width, height = _size(cleaned)
    cleaned.set("xmlns", SVG)
    return CleanSvg(ET.tostring(cleaned, encoding="utf-8", xml_declaration=False), width, height)
