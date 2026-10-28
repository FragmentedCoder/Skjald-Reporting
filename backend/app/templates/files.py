"""Template files (.skjald): a template version as a ZIP, to move between installs.

    manifest.json   the format, the template's UUID, name and version, and each file's SHA-256
    settings.json   who signs, review, numbering, delivery, styles
    questions.json  the form's steps and questions
    layout.json     the PDF's blocks
    rules.json      every expression, by element: "<element id>/<field>"
    strings.json    every piece of text, by element: "<element id>/<path>"
    styles.json     the template's style layers, and the company's default style
    library.json    the shared library entries the template reads
    sample.json     the sample answers for "Try it"
    assets/         the template's images (and the style's, under assets/style/)

questions.json and layout.json hold the whole template; rules.json and strings.json
are the same expressions and text gathered in one place, for review and translation.
On import they're laid over the other two, so a translator can edit strings.json alone.
The browser gathers strings the same way (frontend/src/lib/templates/strings.ts), and
shared/templates/strings.json holds both to the same answer.

Import trusts nothing: the ZIP's size, entry count and expansion are capped; entry
names must be ones listed here (no folders of their own, links or paths outside); each
file must match the manifest's hash and the manifest list every file; JSON is capped
in size and depth and checked against the schema; every expression must pass the
validator; rich text holds only allowed nodes; images are re-encoded and SVGs rebuilt.
An import arrives as a new template's draft, and never changes the library or a style
that's already there.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.cel.engine import ExpressionError, validate
from app.templates.content import TemplateContent
from app.templates.text import doc_expressions, interpolations

FORMAT = "skjald-template"
FORMAT_VERSION = 1
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_ENTRIES = 300
MAX_EXPANDED_BYTES = 60 * 1024 * 1024
MAX_RATIO = 100
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 64
JSON_FILES = ("manifest.json", "settings.json", "questions.json", "layout.json", "rules.json",
              "strings.json", "styles.json", "library.json", "sample.json")
_ASSET = re.compile(r"^assets/(style/)?([0-9a-f]{64})\.(png|jpg|svg)$")
EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg"}

# What's text, and what's an expression, among a template's fields.
TEXT_KEYS = frozenset({"title", "subtitle", "label", "help", "valid_message", "text", "caption",
                       "empty_text", "intro", "placeholder", "pattern_message", "unit",
                       "yes_label", "no_label"})
RICH_KEYS = frozenset({"content", "intro"})
RULE_KEYS = frozenset({"visible_when", "required_when", "valid_when", "default", "tone_rule",
                       "repeat_for", "value"})


class TemplateFileRejected(ValueError):
    """The file can't be imported; the message is fit to show."""


# Strings and rules, by element


def _walk(node: Any, anchor: str, path: list[str], parent_key: str | None
          ) -> Iterator[tuple[str, str, Any, str]]:
    """(kind, address, value, key) for every string and rule under node."""
    if isinstance(node, dict):
        own = node.get("id") if isinstance(node.get("id"), str) else None
        here, rel = (own, []) if own else (anchor, path)
        for key, value in node.items():
            address = "/".join([here, *rel, key])
            if key in RICH_KEYS and isinstance(value, dict) and value.get("type") == "doc":
                yield "rich", address, value, key
            elif isinstance(value, str) and (key in TEXT_KEYS or (
                    key == "value" and parent_key == "facts")):
                if value:  # nothing to translate in an empty one
                    yield "text", address, value, key
            elif key in RULE_KEYS and own and isinstance(value, str):
                yield "rule", address, value, key
            elif isinstance(value, dict | list):
                yield from _walk(value, here, [*rel, key], key)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, anchor, [*path, str(i)], parent_key)


def _parts(content: dict[str, Any]) -> Iterator[tuple[str, str, Any, str]]:
    for part in ("form", "layout"):
        yield from _walk(content[part], part, [], None)


def strings(content: dict[str, Any]) -> dict[str, Any]:
    """Every piece of text (plain and not empty, or a rich text document), by address."""
    return {address: value for kind, address, value, _ in _parts(content) if kind != "rule"}


def rules(content: dict[str, Any]) -> dict[str, str]:
    """Every expression, by address."""
    return {address: value for kind, address, value, _ in _parts(content) if kind == "rule"}


def _set(node: Any, anchor: str, path: list[str], wanted: dict[str, Any], kinds: set[str],
         parent_key: str | None, done: set[str]) -> None:
    if isinstance(node, dict):
        own = node.get("id") if isinstance(node.get("id"), str) else None
        here, rel = (own, []) if own else (anchor, path)
        for key, value in list(node.items()):
            address = "/".join([here, *rel, key])
            if address in wanted:
                rich = key in RICH_KEYS and isinstance(value, dict) and value.get("type") == "doc"
                kind = ("rich" if rich else
                        "text" if isinstance(value, str) and (
                            key in TEXT_KEYS or (key == "value" and parent_key == "facts")) else
                        "rule" if key in RULE_KEYS and own else None)
                if kind in kinds:
                    node[key] = wanted[address]
                    done.add(address)
                    continue
            if isinstance(value, dict | list):
                _set(value, here, [*rel, key], wanted, kinds, key, done)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _set(item, anchor, [*path, str(i)], wanted, kinds, parent_key, done)


def apply(content: dict[str, Any], *, texts: dict[str, Any] | None = None,
          expressions: dict[str, str] | None = None) -> dict[str, Any]:
    """The content with these strings and rules put back by address; an address that
    names nothing (or the wrong kind of thing) is refused with TemplateFileRejected."""
    for wanted, kinds in ((texts or {}, {"text", "rich"}), (expressions or {}, {"rule"})):
        done: set[str] = set()
        for part in ("form", "layout"):
            _set(content[part], part, [], wanted, kinds, None, done)
        missing = sorted(set(wanted) - done)
        if missing:
            raise TemplateFileRejected(f"“{missing[0]}” names nothing in the template.")
    return content


# Writing a file


@dataclass
class Picture:
    sha256: str
    content_type: str
    data: bytes


@dataclass
class Export:
    uuid: str
    name: str
    description: str
    version: int | None
    content: TemplateContent
    pictures: list[Picture] = field(default_factory=list)
    library: list[dict[str, Any]] = field(default_factory=list)
    # {"name": ..., "content": StyleContent as JSON} or None
    style: dict[str, Any] | None = None
    style_pictures: list[Picture] = field(default_factory=list)
    app_version: str = ""
    exported_at: str = ""


def _json(value: Any) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True).encode()


def write(export: Export) -> bytes:
    data = export.content.dump()
    files: dict[str, bytes] = {
        "settings.json": _json(data["settings"]),
        "questions.json": _json(data["form"]),
        "layout.json": _json(data["layout"]),
        "rules.json": _json(rules(data)),
        "strings.json": _json(strings(data)),
        "styles.json": _json({"layers": data["settings"]["styles"],
                              "company_default": export.style}),
        "library.json": _json(export.library),
        "sample.json": _json(data["sample"]),
    }
    for picture in export.pictures:
        files[f"assets/{picture.sha256}.{EXTENSIONS[picture.content_type]}"] = picture.data
    for picture in export.style_pictures:
        files[f"assets/style/{picture.sha256}.{EXTENSIONS[picture.content_type]}"] = picture.data
    manifest = {
        "format": FORMAT, "format_version": FORMAT_VERSION, "schema": data["schema"],
        "template": {"uuid": export.uuid, "name": export.name, "description": export.description,
                     "version": export.version},
        "exported_at": export.exported_at, "skjald_version": export.app_version,
        "files": {name: hashlib.sha256(body).hexdigest() for name, body in sorted(files.items())},
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json(manifest))
        for name, body in sorted(files.items()):
            archive.writestr(name, body)
    return out.getvalue()


# Reading a file


@dataclass
class Imported:
    uuid: str
    name: str
    description: str
    content: dict[str, Any]
    pictures: dict[str, bytes]
    library: list[dict[str, Any]]
    style: dict[str, Any] | None
    style_pictures: dict[str, bytes]


def _depth(value: Any, limit: int = MAX_DEPTH) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > limit:
            raise TemplateFileRejected("The file's data is nested too deeply.")
        if isinstance(node, dict):
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)


def _load_json(name: str, body: bytes) -> Any:
    if len(body) > MAX_JSON_BYTES:
        raise TemplateFileRejected(f"{name} is too large.")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise TemplateFileRejected(f"{name} isn't valid JSON.") from None
    _depth(value)
    return value


def _entries(raw: bytes) -> dict[str, bytes]:
    """The ZIP's files, read within the limits."""
    if len(raw) > MAX_FILE_BYTES:
        raise TemplateFileRejected("The file is larger than 12 MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, ValueError):
        raise TemplateFileRejected("That isn't a Skjald template file.") from None
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise TemplateFileRejected("The file holds too many files.")
        if sum(i.file_size for i in infos) > MAX_EXPANDED_BYTES:
            raise TemplateFileRejected("The file expands to more than Skjald accepts.")
        found: dict[str, bytes] = {}
        for info in infos:
            name = info.filename
            if name in found:
                raise TemplateFileRejected(f"The file lists {name} twice.")
            if (info.is_dir() or stat.S_ISLNK(info.external_attr >> 16)
                    or (name not in JSON_FILES and not _ASSET.match(name))):
                raise TemplateFileRejected(f"The file holds something Skjald doesn't accept: "
                                           f"{name[:80]}")
            if info.flag_bits & 0x1:
                raise TemplateFileRejected("The file is encrypted.")
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
                raise TemplateFileRejected("The file expands to more than Skjald accepts.")
            with archive.open(info) as stream:
                body = stream.read(info.file_size + 1)
            if len(body) != info.file_size:
                raise TemplateFileRejected("The file is damaged.")
            found[name] = body
        return found


def read(raw: bytes) -> Imported:
    """A template file, checked; TemplateFileRejected says what's wrong with it."""
    files = _entries(raw)
    if "manifest.json" not in files:
        raise TemplateFileRejected("That isn't a Skjald template file: it has no manifest.")
    manifest = _load_json("manifest.json", files.pop("manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise TemplateFileRejected("That isn't a Skjald template file.")
    if manifest.get("format_version") != FORMAT_VERSION:
        raise TemplateFileRejected("The file is from a version of Skjald this one can't read.")
    listed = manifest.get("files")
    if not isinstance(listed, dict) or set(listed) != set(files):
        raise TemplateFileRejected("The file's contents don't match its manifest.")
    for name, body in files.items():
        if hashlib.sha256(body).hexdigest() != listed[name]:
            raise TemplateFileRejected(f"{name} doesn't match its manifest: the file was changed "
                                       f"or damaged.")
    for name in JSON_FILES[1:]:
        if name not in files:
            raise TemplateFileRejected(f"The file has no {name}.")
    loaded = {name: _load_json(name, files[name]) for name in JSON_FILES[1:]}
    content: dict[str, Any] = {
        "schema": manifest.get("schema", 1), "settings": loaded["settings.json"],
        "form": loaded["questions.json"], "layout": loaded["layout.json"],
        "sample": loaded["sample.json"],
    }
    texts, expressions = loaded["strings.json"], loaded["rules.json"]
    if not isinstance(texts, dict) or not isinstance(expressions, dict) or not all(
            isinstance(v, str) for v in expressions.values()):
        raise TemplateFileRejected("strings.json and rules.json must map addresses to values.")
    if not isinstance(content["form"], list) or not isinstance(content["layout"], list):
        raise TemplateFileRejected("questions.json and layout.json must be lists.")
    apply(content, texts=texts, expressions=expressions)
    # Names and types are the draft's checks' business; an expression that isn't one
    # Skjald runs at all (unreadable, too long, a function it doesn't have, matches())
    # isn't imported.
    found = list(rules(content).items())
    for address, text in strings(content).items():
        found += [(address, expr) for expr in (
            doc_expressions(text) if isinstance(text, dict)
            else [part.expr for part in interpolations(text)] if isinstance(text, str) else [])]
    for address, expr in found:
        try:
            validate(expr, ())
        except ExpressionError as exc:
            raise TemplateFileRejected(f"The rule at {address} can't be imported: "
                                       f"{exc.message}") from None
    given = manifest.get("template")
    template: dict[str, Any] = given if isinstance(given, dict) else {}
    styles = loaded["styles.json"] if isinstance(loaded["styles.json"], dict) else {}
    library = loaded["library.json"]
    if not isinstance(library, list) or not all(isinstance(e, dict) for e in library):
        raise TemplateFileRejected("library.json must be a list of entries.")
    pictures = {m.group(2): body for name, body in files.items()
                if (m := _ASSET.match(name)) and not m.group(1)}
    style_pictures = {m.group(2): body for name, body in files.items()
                      if (m := _ASSET.match(name)) and m.group(1)}
    style = styles.get("company_default")
    return Imported(
        uuid=str(template.get("uuid") or ""),
        name=str(template.get("name") or "Imported template"),
        description=str(template.get("description") or ""), content=content, pictures=pictures,
        library=library, style=style if isinstance(style, dict) else None,
        style_pictures=style_pictures,
    )
