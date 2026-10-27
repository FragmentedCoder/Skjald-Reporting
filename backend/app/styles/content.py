"""What a report style holds, and how styles stack.

Styles stack in layers: the Skjald default (default.json, a copy of shared/styles/
default.json that a test holds to it), then a company style, then a customer style.
A style stores only what it changes from the layer below, and resolve() stacks the
layers into the whole look a report prints with. The browser stacks them the same
way (frontend/src/lib/reportStyles/resolve.ts); shared/styles/cases.json holds both to
the same answers.

- colours: text, muted text, headings, the accent, links, lines, the table header's
  fill and text, and the classification label.
- tones: a fill and a text colour for each callout tone.
- fonts: the heading and body fonts, from the three bundled with Skjald.
- sizes: body text and the cover's title, in points.
- margins: where a page's text goes, in millimetres.
- pages: the designs of the cover, the first page and the other pages: what is
  placed around the text (logos, text with variables, lines, boxes, images, the
  report number, the classification, "Page X of Y"), measured in millimetres from
  the page's top left.
- artwork: finished artwork drawn behind the first page and behind the rest.

Colours, fonts, sizes and margins stack key by key and a tone as a pair; a page
design and the artwork replace the layer below's as a whole. A customer's own
report background (app/backgrounds.py) goes over the artwork, with its margins,
when the template uses it.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.cel.engine import Engine, ExpressionError
from app.templates.names import CONTEXT
from app.templates.text import interpolations

DEFAULT: dict[str, Any] = {
    key: value
    for key, value in json.loads((Path(__file__).parent / "default.json").read_text()).items()
    if key != "about"
}
PAGE_WIDTH, PAGE_HEIGHT = 210, 297
MAX_ELEMENTS = 60

Hex = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$", to_upper=True)]
# A colour of the style's own, by name, or any colour.
ColourRef = Annotated[str, StringConstraints(
    pattern=r"^(#[0-9A-Fa-f]{6}|text|muted|heading|accent|link|line|classification)$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Font = Literal["marcellus", "plex-sans", "plex-mono"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Colours(Strict):
    text: Hex | None = None
    muted: Hex | None = None
    heading: Hex | None = None
    accent: Hex | None = None
    link: Hex | None = None
    line: Hex | None = None
    table_head: Hex | None = None
    table_head_text: Hex | None = None
    classification: Hex | None = None


class Tone(Strict):
    fill: Hex
    ink: Hex


class Tones(Strict):
    info: Tone | None = None
    note: Tone | None = None
    warning: Tone | None = None
    critical: Tone | None = None
    success: Tone | None = None


class Fonts(Strict):
    heading: Font | None = None
    body: Font | None = None


class Sizes(Strict):
    body: float | None = Field(default=None, ge=8, le=14)
    title: float | None = Field(default=None, ge=16, le=48)


class Margins(Strict):
    top: float | None = Field(default=None, ge=5, le=80)
    bottom: float | None = Field(default=None, ge=5, le=80)
    left: float | None = Field(default=None, ge=5, le=60)
    right: float | None = Field(default=None, ge=5, le=60)


class Element(Strict):
    id: Annotated[str, StringConstraints(pattern=r"^e_[a-z0-9]{4,32}$")]
    kind: Literal["text", "logo", "image", "line", "box", "page_number", "classification",
                  "report_number"]
    x: float = Field(ge=0, le=PAGE_WIDTH)
    y: float = Field(ge=0, le=PAGE_HEIGHT)
    w: float = Field(ge=0, le=PAGE_WIDTH)
    h: float = Field(ge=0, le=PAGE_HEIGHT)
    # A text element's words, with {{ expressions }} reading the report's context.
    text: str = Field(default="", max_length=500)
    font: Literal["heading", "body", "mono"] = "body"
    size: float = Field(default=9, ge=5, le=48)
    colour: ColourRef = "text"
    weight: Literal["regular", "bold"] = "regular"
    align: Literal["left", "center", "right"] = "left"
    logo: Literal["company", "customer"] = "company"
    # An image element's picture, one of the style's own.
    asset: Sha256 | None = None
    # Boxes are filled and outlined; lines are drawn with the stroke alone.
    fill: ColourRef | None = None
    stroke: ColourRef | None = "line"
    stroke_width: float = Field(default=0.3, ge=0, le=5)
    radius: float = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def _fits(self) -> Element:
        if self.x + self.w > PAGE_WIDTH + 0.01 or self.y + self.h > PAGE_HEIGHT + 0.01:
            raise ValueError("An element must fit on the page (210 × 297 mm).")
        if self.kind == "image" and self.asset is None:
            raise ValueError("An image element needs a picture.")
        return self


class PageDesign(Strict):
    elements: list[Element] = Field(default_factory=list, max_length=MAX_ELEMENTS)

    @field_validator("elements")
    @classmethod
    def _unique(cls, elements: list[Element]) -> list[Element]:
        if len({e.id for e in elements}) != len(elements):
            raise ValueError("Two elements share an ID.")
        return elements


class Pages(Strict):
    cover: PageDesign | None = None
    first: PageDesign | None = None
    other: PageDesign | None = None


class Artwork(Strict):
    # None: a plain page.
    first: Sha256 | None = None
    other: Sha256 | None = None


class StyleContent(Strict):
    colours: Colours = Field(default_factory=Colours)
    tones: Tones = Field(default_factory=Tones)
    fonts: Fonts = Field(default_factory=Fonts)
    sizes: Sizes = Field(default_factory=Sizes)
    margins: Margins = Field(default_factory=Margins)
    pages: Pages = Field(default_factory=Pages)
    # None: the layer below's artwork.
    artwork: Artwork | None = None


# The whole look, once stacked: every value set.


class ResolvedColours(Strict):
    text: Hex
    muted: Hex
    heading: Hex
    accent: Hex
    link: Hex
    line: Hex
    table_head: Hex
    table_head_text: Hex
    classification: Hex


class ResolvedTones(Strict):
    info: Tone
    note: Tone
    warning: Tone
    critical: Tone
    success: Tone


class ResolvedFonts(Strict):
    heading: Font
    body: Font


class ResolvedSizes(Strict):
    body: float
    title: float


class ResolvedMargins(Strict):
    top: float
    bottom: float
    left: float
    right: float


class ResolvedPages(Strict):
    cover: PageDesign
    first: PageDesign
    other: PageDesign


class ResolvedStyle(Strict):
    colours: ResolvedColours
    tones: ResolvedTones
    fonts: ResolvedFonts
    sizes: ResolvedSizes
    margins: ResolvedMargins
    pages: ResolvedPages
    artwork: Artwork


def resolve(layers: Sequence[StyleContent]) -> ResolvedStyle:
    """The Skjald default with each layer stacked on it, bottom first."""
    merged = copy.deepcopy(DEFAULT)
    for layer in layers:
        data = layer.model_dump()
        for group in ("colours", "tones", "fonts", "sizes", "margins"):
            merged[group].update({k: v for k, v in data[group].items() if v is not None})
        for page, design in data["pages"].items():
            if design is not None:
                merged["pages"][page] = design
        if data["artwork"] is not None:
            merged["artwork"] = data["artwork"]
    return ResolvedStyle.model_validate(merged)


def assets(content: StyleContent) -> set[str]:
    """The pictures a style's content uses, by SHA-256."""
    used = {e.asset for design in (content.pages.cover, content.pages.first, content.pages.other)
            if design for e in design.elements if e.asset}
    if content.artwork:
        used |= {sha for sha in (content.artwork.first, content.artwork.other) if sha}
    return used


PAGE_NAMES = {"cover": "the cover", "first": "the first page", "other": "the other pages"}


def problems(content: StyleContent, *, timezone: str,
             library: Mapping[str, str] | None = None) -> list[str]:
    """What's wrong with the expressions in a style's text elements, in plain words.

    They read the report's context and the shared library, never a template's answers:
    a style serves every template."""
    engine = Engine({**CONTEXT, **(library or {})}, timezone=timezone)
    found = []
    for page, where in PAGE_NAMES.items():
        design = getattr(content.pages, page)
        for number, element in enumerate(design.elements if design else [], start=1):
            if element.kind != "text":
                continue
            for part in interpolations(element.text):
                if not part.closed:
                    found.append(f"Element {number} on {where}: a {{{{ has no }}}} to close it.")
                    continue
                try:
                    engine.check(part.expr)
                except ExpressionError as exc:
                    found.append(f"Element {number} on {where}: {exc.message}")
    return found
