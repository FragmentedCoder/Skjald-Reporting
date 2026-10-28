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


def table_from_csv(text: str) -> dict[str, Any]:
    """A CSV file's rows as a table: the first row names the columns, the first column
    holds the keys."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if len(rows) < 2 or len(rows[0]) < 2:
        raise ValueError("The file needs a header row and at least one row, each with a key "
                         "and a value.")
    header = [cell.strip() for cell in rows[0]]
    width = len(header)
    found: dict[str, list[str]] = {}
    for row in rows[1:]:
        cells = [cell.strip() for cell in row] + [""] * (width - len(row))
        found[cells[0]] = cells[1:width]
    return parse_value("table", {"key_label": header[0], "columns": header[1:], "rows": found})


def table_from_json(text: str) -> dict[str, Any]:
    """{"key": "value"}, {"key": {"column": "value"}} or [{"key": ..., "column": ...}]."""
    data = json.loads(text)
    if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        return parse_value("table", {"columns": ["Value"],
                                     "rows": {k: [v] for k, v in data.items()}})
    records: list[dict[str, Any]]
    if isinstance(data, dict):
        records = [{"key": k, **v} for k, v in data.items() if isinstance(v, dict)]
        key_name = "key"
    elif isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        records = data
        key_name = next(iter(records[0]))
    else:
        raise ValueError("Use an object of keys and values, or a list of objects.")
    columns = [c for c in records[0] if c != key_name]
    return parse_value("table", {
        "key_label": key_name, "columns": columns,
        "rows": {str(r.get(key_name, "")): [str(r.get(c, "")) for c in columns] for r in records},
    })


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
