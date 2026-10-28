"""Text in templates: rich text, and expressions written inside {{ }}.

Rich text is the editor's (TipTap's) JSON document, checked node by node against
the few kinds Skjald prints: paragraphs, two heading levels, lists, line breaks,
bold, italic, underline, strike-through, code, links (https, http and mailto only)
and variables. Anything else, unknown attributes included, is refused, so nothing a
browser or the renderer would run can arrive this way.

Plain text such as a title or a caption can hold expressions in {{ }}, as can rich
text through variable nodes. The browser finds them the same way
(frontend/src/lib/templates/text.ts).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

MAX_NODES = 5000
MAX_DEPTH = 12
MAX_TEXT = 100_000
LINK_SCHEMES = ("https://", "http://", "mailto:")
MARKS = frozenset({"bold", "italic", "underline", "strike", "code", "link"})


class RichTextError(ValueError):
    pass


@dataclass
class _Walk:
    nodes: int = 0
    text: int = 0


def _keys(node: dict[str, Any], allowed: set[str], where: str) -> None:
    extra = set(node) - allowed
    if extra:
        raise RichTextError(f"{where} has unexpected parts: {', '.join(sorted(extra))}.")


def _content(node: dict[str, Any], where: str) -> list[Any]:
    content = node.get("content", [])
    if not isinstance(content, list):
        raise RichTextError(f"{where} content must be a list.")
    return content


def _inline(node: Any, walk: _Walk) -> None:
    if not isinstance(node, dict):
        raise RichTextError("Text must be made of nodes.")
    walk.nodes += 1
    kind = node.get("type")
    if kind == "text":
        _keys(node, {"type", "text", "marks"}, "Text")
        text = node.get("text")
        if not isinstance(text, str) or not text:
            raise RichTextError("A text node needs its text.")
        walk.text += len(text)
        marks = node.get("marks", [])
        if not isinstance(marks, list):
            raise RichTextError("Marks must be a list.")
        for mark in marks:
            if not isinstance(mark, dict) or mark.get("type") not in MARKS:
                raise RichTextError("Text can be bold, italic, underlined, struck through, code "
                                    "or a link, nothing else.")
            if mark["type"] == "link":
                _keys(mark, {"type", "attrs"}, "A link")
                attrs = mark.get("attrs")
                if not isinstance(attrs, dict) or set(attrs) != {"href"}:
                    raise RichTextError("A link needs its address, and nothing else.")
                href = attrs["href"]
                if (not isinstance(href, str) or not href.startswith(LINK_SCHEMES)
                        or len(href) > 2000):
                    raise RichTextError("Links must start with https://, http:// or mailto:.")
            else:
                _keys(mark, {"type"}, "A mark")
    elif kind == "hardBreak":
        _keys(node, {"type"}, "A line break")
    elif kind == "variable":
        _keys(node, {"type", "attrs"}, "A variable")
        attrs = node.get("attrs")
        if (not isinstance(attrs, dict) or set(attrs) != {"expr"}
                or not isinstance(attrs["expr"], str)):
            raise RichTextError("A variable needs its expression, and nothing else.")
    else:
        raise RichTextError(f"Text can't hold a {kind!r} node.")


def _block(node: Any, walk: _Walk, depth: int) -> None:
    if not isinstance(node, dict):
        raise RichTextError("Rich text must be made of nodes.")
    if depth > MAX_DEPTH:
        raise RichTextError("Rich text is nested too deeply.")
    walk.nodes += 1
    if walk.nodes > MAX_NODES or walk.text > MAX_TEXT:
        raise RichTextError("Rich text is too long.")
    kind = node.get("type")
    if kind == "paragraph":
        _keys(node, {"type", "content"}, "A paragraph")
        for child in _content(node, "A paragraph"):
            _inline(child, walk)
    elif kind == "heading":
        _keys(node, {"type", "attrs", "content"}, "A heading")
        attrs = node.get("attrs")
        if not isinstance(attrs, dict) or set(attrs) != {"level"} or attrs["level"] not in (3, 4):
            raise RichTextError("Headings in text are level 3 or 4.")
        for child in _content(node, "A heading"):
            _inline(child, walk)
    elif kind in ("bulletList", "orderedList"):
        _keys(node, {"type", "attrs", "content"} if kind == "orderedList" else {"type", "content"},
              "A list")
        if kind == "orderedList" and "attrs" in node:
            attrs = node["attrs"]
            if not isinstance(attrs, dict) or not set(attrs) <= {"start", "type"}:
                raise RichTextError("A numbered list has a start number, and nothing else.")
            start = attrs.get("start", 1)
            if not isinstance(start, int) or isinstance(start, bool) or not 1 <= start <= 10_000:
                raise RichTextError("A numbered list starts at a number from 1.")
            if attrs.get("type") not in (None, "1"):
                raise RichTextError("A numbered list uses numbers.")
        items = _content(node, "A list")
        if not items:
            raise RichTextError("A list needs at least one item.")
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "listItem":
                raise RichTextError("A list holds list items only.")
            walk.nodes += 1
            _keys(item, {"type", "content"}, "A list item")
            children = _content(item, "A list item")
            first = children[0] if children else None
            if not isinstance(first, dict) or first.get("type") != "paragraph":
                raise RichTextError("A list item starts with a paragraph.")
            for child in children:
                if not isinstance(child, dict) or child.get("type") not in (
                        "paragraph", "bulletList", "orderedList"):
                    raise RichTextError("A list item holds paragraphs and lists.")
                _block(child, walk, depth + 1)
    else:
        raise RichTextError(f"Rich text can't hold a {kind!r} node.")


def check_doc(doc: Any) -> dict[str, Any]:
    """The document, if it holds only what Skjald prints; else RichTextError."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise RichTextError("Rich text must be a document.")
    _keys(doc, {"type", "content"}, "The document")
    walk = _Walk()
    for node in _content(doc, "The document"):
        _block(node, walk, 1)
    return doc


def doc_expressions(doc: dict[str, Any]) -> Iterator[str]:
    """The expressions in a document: its variables', then those in {{ }} in its text."""
    def nodes(node: Any) -> Iterator[dict[str, Any]]:
        if isinstance(node, dict):
            yield node
            for child in node.get("content", []):
                yield from nodes(child)
    for node in nodes(doc):
        if node.get("type") == "variable":
            yield node["attrs"]["expr"]
        elif node.get("type") == "text":
            for found in interpolations(node["text"]):
                yield found.expr


def doc_text(doc: dict[str, Any]) -> str:
    """The document's words, paragraphs on their own lines, for expressions to read."""
    lines: list[str] = []

    def inline(node: dict[str, Any]) -> str:
        kind = node.get("type")
        if kind == "text":
            return str(node["text"])
        if kind == "hardBreak":
            return "\n"
        return ""

    def block(node: dict[str, Any]) -> None:
        if node.get("type") in ("paragraph", "heading"):
            lines.append("".join(inline(child) for child in node.get("content", [])))
        else:
            for child in node.get("content", []):
                block(child)
    block(doc)
    return "\n".join(lines)


@dataclass(frozen=True)
class Interpolation:
    start: int
    end: int
    expr: str
    closed: bool = True


def interpolations(text: str) -> list[Interpolation]:
    """Each {{ expression }} in the text. An expression ends at the first }} outside
    quotes and outside braces of its own, so a map such as {"a": {"b": 1}} fits."""
    found: list[Interpolation] = []
    i = 0
    while (start := text.find("{{", i)) >= 0:
        j = start + 2
        depth = 0
        quote: str | None = None
        end = -1
        while j < len(text):
            c = text[j]
            if quote is not None:
                if c == "\\":
                    j += 2
                    continue
                if text.startswith(quote, j):
                    j += len(quote)
                    quote = None
                    continue
                j += 1
                continue
            if c in ("'", '"'):
                quote = c * 3 if text.startswith(c * 3, j) else c
                j += len(quote)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if depth == 0 and text.startswith("}}", j):
                    end = j
                    break
                depth = max(depth - 1, 0)
            j += 1
        if end < 0:
            found.append(Interpolation(start, len(text), text[start + 2:].strip(), closed=False))
            break
        found.append(Interpolation(start, end + 2, text[start + 2:end].strip()))
        i = end + 2
    return found
