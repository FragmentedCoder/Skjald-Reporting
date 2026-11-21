"""What each kind of library entry holds, and what templates read from the library.

A variable holds one line of text (vars.<key>); a text snippet holds paragraphs
(text.<key>), which may use variables in {{ }} but never other snippets, so a
snippet can't loop; a data table holds rows of values by key, one per column, for
lookup(). Tables can be imported from CSV or JSON.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.cel.library import Table
from app.library.models import LibraryEntry, LibraryVersion
from app.templates.text import interpolations

Kind = Literal["variable", "snippet", "table"]
KEY_PATTERN = r"^[a-z][a-z0-9_]{0,49}$"
MAX_ROWS = 5000
MAX_COLUMNS = 10
_VARIABLE = re.compile(r"^vars\.([a-z][a-z0-9_]{0,49})$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VariableValue(Strict):
    value: str = Field(max_length=2000)


class SnippetValue(Strict):
    text: str = Field(max_length=20_000)

    @field_validator("text")
    @classmethod
    def _only_variables(cls, text: str) -> str:
        for found in interpolations(text):
            if not found.closed or not _VARIABLE.match(found.expr):
                raise ValueError("A snippet can use variables, such as {{vars.support_phone}}, "
                                 "but not other snippets or expressions.")
        return text


class TableValue(Strict):
    # What the key column is, for people, such as "Score".
    key_label: str = Field(default="Key", min_length=1, max_length=100)
    columns: list[str] = Field(min_length=1, max_length=MAX_COLUMNS)
    rows: dict[str, list[str]] = Field(max_length=MAX_ROWS)

    @model_validator(mode="after")
    def _shape(self) -> TableValue:
        if any(not c.strip() or len(c) > 100 for c in self.columns):
            raise ValueError("Every column needs a name of up to 100 characters.")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("Two columns have the same name.")
        for key, row in self.rows.items():
            if not key or len(key) > 200:
                raise ValueError("Every row needs a key of up to 200 characters.")
            if len(row) != len(self.columns) or any(len(v) > 2000 for v in row):
                raise ValueError(f"The row {key!r} needs one value for each column.")
        return self


MODELS: dict[str, type[Strict]] = {
    "variable": VariableValue, "snippet": SnippetValue, "table": TableValue,
}


def parse_value(kind: str, raw: Any) -> dict[str, Any]:
    return MODELS[kind].model_validate(raw).model_dump()


def _delimiter(line: str) -> str:
    """Commas, unless the header has none and is split by semicolons (as spreadsheets
    write CSV where the comma is the decimal sign) or tabs."""
    if "," in line:
        return ","
    return ";" if ";" in line else "\t" if "\t" in line else ","


def _keyed(rows: Iterable[tuple[str, list[str]]]) -> dict[str, list[str]]:
    """The rows by key: each needs one, and one of its own."""
    found: dict[str, list[str]] = {}
    for number, (key, cells) in enumerate(rows, start=1):
        if not key:
            raise ValueError(f"Row {number} has no key.")
        if key in found:
            raise ValueError(f"The key {key!r} is there twice: each row needs a key of its "
                             "own.")
        found[key] = cells
    return found


def table_from_csv(text: str) -> dict[str, Any]:
    """A CSV file's rows as a table: the first row names the columns, the first column
    holds the keys. Semicolons or tabs separate where the header has no commas."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    first = next((line for line in text.split("\n") if line.strip()), "")
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=_delimiter(first), strict=True))
    except csv.Error as exc:
        raise ValueError("That file can't be read as CSV: check its quotes, and that no cell "
                         "is longer than 2,000 characters.") from exc
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if len(rows) < 2 or len(rows[0]) < 2:
        raise ValueError("The file needs a header row and at least one row, each with a key "
                         "and a value.")
    header = [cell.strip() for cell in rows[0]]
    width = len(header)
    for number, row in enumerate(rows[1:], start=1):
        if any(cell.strip() for cell in row[width:]):
            raise ValueError(f"Row {number} has more cells than the header names columns.")
    found = _keyed((cells[0], cells[1:width]) for cells in (
        [cell.strip() for cell in row[:width]] + [""] * (width - len(row)) for row in rows[1:]))
    return parse_value("table", {"key_label": header[0], "columns": header[1:], "rows": found})


def _cell(value: Any) -> str:
    """A JSON value as a cell: text and numbers as written, nothing as empty."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    raise ValueError("Each value must be text or a number, not a list or an object.")


def table_from_json(text: str) -> dict[str, Any]:
    """{"key": "value"}, {"key": {"column": "value"}} or [{"key": ..., "column": ...}]."""
    try:
        data = json.loads(text.lstrip("\ufeff"))
    except RecursionError as exc:
        raise ValueError("That file is nested too deeply to be a table.") from exc
    shape = "Use an object of keys and values, or a list of objects."
    if isinstance(data, dict) and data:
        inner = [isinstance(v, dict) for v in data.values()]
        if not any(inner):
            return parse_value("table", {"columns": ["Value"], "rows": _keyed(
                (str(k), [_cell(v)]) for k, v in data.items())})
        if not all(inner):
            raise ValueError("Give every key a value, or every key an object of columns, "
                             "not some of each.")
        columns = list(next(iter(data.values())))
        if not columns:
            raise ValueError(shape)
        return parse_value("table", {"columns": columns, "rows": _keyed(
            (str(k), [_cell(v.get(c)) for c in columns]) for k, v in data.items())})
    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        key_name, *columns = list(data[0]) or [""]
        if not columns:
            raise ValueError("Each object needs a key first, then at least one value.")
        return parse_value("table", {"key_label": key_name, "columns": columns, "rows": _keyed(
            (_cell(r.get(key_name)), [_cell(r.get(c)) for c in columns]) for r in data)})
    raise ValueError(shape)


def library_names(entries: Iterable[LibraryEntry]) -> dict[str, str]:
    """The names templates can read from the library, and their types."""
    prefix = {"variable": "vars", "snippet": "text"}
    return {f"{prefix[e.kind]}.{e.key}": "string" for e in entries
            if e.kind in prefix and e.removed_at is None}


def library_values(entries: Iterable[tuple[LibraryEntry, LibraryVersion]]
                   ) -> tuple[dict[str, dict[str, str]], dict[str, Table]]:
    """What templates read: {"vars": ..., "text": ...} with snippets' variables filled
    in, and the data tables for lookup()."""
    variables: dict[str, str] = {}
    snippets: dict[str, str] = {}
    tables: dict[str, Table] = {}
    for entry, version in entries:
        if entry.removed_at is not None:
            continue
        value = json.loads(version.value)
        if entry.kind == "variable":
            variables[entry.key] = value["value"]
        elif entry.kind == "snippet":
            snippets[entry.key] = value["text"]
        else:
            tables[entry.key] = Table(value["columns"], value["rows"])
    filled = {}
    for key, text in snippets.items():
        out, last = "", 0
        for found in interpolations(text):
            name = found.expr.split(".", 1)[1]
            out += text[last:found.start] + variables.get(name, "")
            last = found.end
        filled[key] = out + text[last:]
    return {"vars": variables, "text": filled}, tables
