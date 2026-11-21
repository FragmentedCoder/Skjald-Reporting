"""SVG pictures, cleaned before Skjald stores them.

An SVG is a document, and can carry scripts, links to other sites, styles that load
things and entities that blow up when expanded. So the file is parsed with
defusedxml (no DTDs, so no entities) and rebuilt from an allowlist: shapes, paths,
text, gradients, clipping and masks, with their drawing attributes. Everything
else is dropped, including script, style, foreignObject, animation and links. The
only references kept are to the picture's own parts (#id) and embedded PNG or JPEG
data, and a value may call only the functions drawing needs: url() for those parts,
colours and transforms. A picture whose parts refer to each other so often that it
would draw more than MAX_DRAWN elements (a few lines that unfold into a billion
shapes), or in a loop, is refused. The cleaned file is what gets stored and printed.
"""

from __future__ import annotations

import math
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
# The most elements drawing the picture may take, each counted every time a <use>, a
# pattern, a mask or a clip path draws it again.
MAX_DRAWN = 200_000
# The longest a side may be, in the picture's own units: far beyond any real artwork
# (an A0 sheet in thousandths of a millimetre is 1,189,000), and a number that can be kept.
MAX_SIDE = 10_000_000

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
# The only url() a value may hold: a whole one, naming one of the picture's own parts.
_LOCAL_URL = re.compile(r"url\(\s*(['\"]?)#([A-Za-z_][\w.\-]*)\1\s*\)", re.IGNORECASE)
_LOCAL = re.compile(r"^#[A-Za-z_][\w.\-]*$")
# The other functions a value may call: colours and transforms. A bracket opened after
# anything else is refused, url() that isn't as above included: image-set() and image()
# load pictures from addresses written as plain text, and a url( left open still loads.
_FUNCTIONS = frozenset({"rgb", "rgba", "hsl", "hsla", "matrix", "translate", "scale", "rotate",
                        "skewx", "skewy"})
_CALL = re.compile(r"([^\s(),;]*)\s*\(")
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
    # A backslash escapes a character in CSS, which reads u\72l( as url(: no value
    # needs one.
    if "\\" in value or "javascript:" in lowered or "@import" in lowered:
        return False
    if name == "href":
        return bool(_LOCAL.match(value) or _DATA_IMAGE.match(value))
    rest = _LOCAL_URL.sub(" ", value)
    return all(call.lower() in _FUNCTIONS for call in _CALL.findall(rest))


def _styles(style: str) -> dict[str, str]:
    """A style attribute's declarations, such as fill:#000;stroke:none, as attributes."""
    found = {}
    for declaration in style.split(";"):
        name, colon, value = declaration.partition(":")
        name, value = name.strip().lower(), value.strip()
        if colon and name in ATTRIBUTES and name != "href" and _value_ok(name, value):
            found[name] = value
    return found


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
    # Drawing set in a style attribute (as PDF converters write it) is kept as the
    # plain attributes it stands for; the style attribute itself never is.
    for name, value in _styles(element.attrib.get("style", "")).items():
        clean.set(name, value)
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


def _references(element: ET.Element) -> list[str]:
    """The IDs of the picture's parts this element draws or draws with."""
    found = [element.get("href", "")[1:]] if element.get("href", "").startswith("#") else []
    for name, value in element.attrib.items():
        if name != "href" and "(" in value:
            found += [ref for _, ref in _LOCAL_URL.findall(value)]
    return found


def _check_drawn(root: ET.Element) -> None:
    """Refuse a picture that takes more than MAX_DRAWN elements to draw once every
    reference is followed, or whose references go round in a loop. An element costs
    itself, what it holds and what it refers to; worked out without recursion, since a
    chain of references can be as long as the file allows."""
    parts: dict[str, ET.Element] = {}
    for element in root.iter():
        if element.get("id"):
            parts.setdefault(element.get("id", ""), element)
    cost: dict[ET.Element, int | None] = {}  # None: being worked out, so met again in a loop
    needs: dict[ET.Element, list[ET.Element]] = {}
    stack = [root]
    while stack:
        element = stack[-1]
        if element not in cost:
            cost[element] = None
            needs[element] = [*element, *(parts[ref] for ref in _references(element)
                                          if ref in parts)]
            if any(cost.get(needed, 0) is None for needed in needs[element]):
                raise SvgRejected("The SVG has a part that draws itself, so it can't be used.")
            stack.extend(needed for needed in needs[element] if needed not in cost)
            continue
        stack.pop()
        if cost[element] is None:
            total = 1 + sum(cost[needed] or 0 for needed in needs.pop(element))
            if total > MAX_DRAWN:
                raise SvgRejected("The SVG is too complex to use.")
            cost[element] = total


def _size(root: ET.Element) -> tuple[int, int]:
    found: tuple[float, float] | None = None
    view_box = root.get("viewBox", "").replace(",", " ").split()
    if len(view_box) == 4:
        try:
            width, height = float(view_box[2]), float(view_box[3])
            if width > 0 and height > 0:
                found = width, height
        except ValueError:
            pass
    sizes = [_LENGTH.match(root.get(name, "")) for name in ("width", "height")]
    if found is None and sizes[0] and sizes[1]:
        found = float(sizes[0].group(1)), float(sizes[1].group(1))
    if found is None:
        raise SvgRejected("The SVG needs a viewBox, or a width and height, so it can be sized.")
    # float() reads "inf" and "1e999" as infinity, and takes any number of digits.
    if not all(math.isfinite(side) and side <= MAX_SIDE for side in found):
        raise SvgRejected("The SVG's size is too large for Skjald to use: its viewBox, or its "
                          f"width and height, can be at most {MAX_SIDE:,} across.")
    return max(1, round(found[0])), max(1, round(found[1]))


def clean_svg(raw: bytes, max_bytes: int = MAX_BYTES) -> CleanSvg:
    if len(raw) > max_bytes:
        raise SvgRejected(f"The SVG is larger than {max_bytes // (1024 * 1024)} MB.")
    try:
        root = fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ET.ParseError, ValueError) as exc:
        raise SvgRejected("That file isn't an SVG Skjald can read.") from exc
    if root.tag != "{" + SVG + "}svg":
        raise SvgRejected("That file isn't an SVG picture.")
    cleaned = _clean(root, 1, [0])
    assert cleaned is not None
    _check_drawn(cleaned)
    width, height = _size(cleaned)
    cleaned.set("xmlns", SVG)
    return CleanSvg(ET.tostring(cleaned, encoding="utf-8", xml_declaration=False), width, height)
