"""Skjald's function library on the server: what templates may call, and the
functions Skjald adds to Google's CEL engine.

shared/cel/functions.json is the list both engines follow; a test holds these
declarations to it. The browser's copy is frontend/src/lib/cel/library.ts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import re2

from app.cel import dates, numbers

# Every function a template may call. The rest of each engine's built-ins (the
# strings extension's reverse() and format(), for instance) are refused, so an
# expression that works on the server works in the browser too.
ALLOWED = frozenset({
    "xor", "switch", "re_match", "re_replace", "replace", "size", "contains",
    "startsWith", "endsWith", "upperAscii", "lowerAscii", "trim", "split", "join",
    "substring", "indexOf", "int", "double", "string", "format_number", "sum", "has",
    "exists", "all", "exists_one", "filter", "map", "lookup", "timestamp", "duration",
    "date", "add_hours", "add_days", "hours_between", "days_between", "format_date",
})

BANNED = {
    "matches": "matches() isn't allowed in templates: use re_match(), which uses the "
               "same safe regular expressions on the server and in the browser.",
}

# The overloads Skjald implements, by ID, with their signatures.
SIGNATURES: dict[str, str] = {
    "xor_bool_bool": "xor(bool, bool): bool",
    "switch_string_string": "switch(string, map<string, string>, string): string",
    "switch_int_string": "switch(int, map<int, string>, string): string",
    "switch_string_double": "switch(string, map<string, double>, double): double",
    "switch_string_int": "switch(string, map<string, int>, int): int",
    "re_match_string_string": "re_match(string, string): bool",
    "re_replace_string_string_string": "re_replace(string, string, string): string",
    "format_number_double_int": "format_number(double, int): string",
    "format_number_int_int": "format_number(int, int): string",
    "sum_list": "sum(list<dyn>): dyn",
    "lookup_string_string": "lookup(string, string): string",
    "lookup_string_string_string": "lookup(string, string, string): string",
    "date_string": "date(string): timestamp",
    "add_hours_timestamp_int": "add_hours(timestamp, int): timestamp",
    "add_days_timestamp_int": "add_days(timestamp, int): timestamp",
    "hours_between_timestamp_timestamp": "hours_between(timestamp, timestamp): double",
    "days_between_timestamp_timestamp": "days_between(timestamp, timestamp): int",
    "format_date_timestamp_string": "format_date(timestamp, string): string",
}


@dataclass(frozen=True)
class Table:
    """A shared library data table: rows of values by key, one per column."""

    columns: Sequence[str]
    rows: Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class Context:
    """What the functions need beyond their arguments."""

    zone: ZoneInfo
    locale: Mapping[str, Any]
    tables: Mapping[str, Table] = field(default_factory=dict)


@lru_cache(maxsize=256)
def _regex(pattern: str) -> Any:
    options = re2.Options()
    options.log_errors = False
    return re2.compile(pattern, options)


def replacement_template(replacement: str) -> str:
    """Skjald's replacement text ($1, ${name}, $$) as RE2's (\\g<1>, \\g<name>, $)."""
    out: list[str] = []
    i = 0
    while i < len(replacement):
        c = replacement[i]
        if c == "\\":
            out.append("\\\\")
        elif c == "$" and replacement.startswith("$$", i):
            out.append("$")
            i += 1
        elif c == "$" and replacement.startswith("${", i) and "}" in replacement[i:]:
            end = replacement.index("}", i)
            out.append(f"\\g<{replacement[i + 2:end]}>")
            i = end
        elif c == "$" and i + 1 < len(replacement) and replacement[i + 1].isdigit():
            j = i + 1
            while j < len(replacement) and replacement[j].isdigit():
                j += 1
            out.append(f"\\g<{replacement[i + 1:j]}>")
            i = j - 1
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _sum(items: list[Any]) -> int | float:
    total: int | float = sum(items)
    if all(isinstance(x, int) and not isinstance(x, bool) for x in items):
        return int(total)
    return float(total)


def _lookup(context: Context, table: str, key: str, column: str | None = None) -> str:
    found = context.tables.get(table)
    if found is None or key not in found.rows:
        return ""
    row = found.rows[key]
    index = 0 if column is None else (
        list(found.columns).index(column) if column in found.columns else -1
    )
    return row[index] if 0 <= index < len(row) else ""


def implementations(context: Context) -> dict[str, Callable[..., Any]]:
    zone, locale = context.zone, context.locale
    return {
        "xor_bool_bool": lambda a, b: a != b,
        "switch_string_string": lambda v, cases, default: cases.get(v, default),
        "switch_int_string": lambda v, cases, default: cases.get(v, default),
        "switch_string_double": lambda v, cases, default: cases.get(v, default),
        "switch_string_int": lambda v, cases, default: cases.get(v, default),
        "re_match_string_string": lambda text, pattern: _regex(pattern).search(text) is not None,
        "re_replace_string_string_string": lambda text, pattern, replacement: _regex(
            pattern).sub(replacement_template(replacement), text),
        "format_number_double_int": lambda value, places: numbers.format_number(
            value, places, locale["decimal"], locale["group"]),
        "format_number_int_int": lambda value, places: numbers.format_number(
            value, places, locale["decimal"], locale["group"]),
        "sum_list": _sum,
        "lookup_string_string": lambda table, key: _lookup(context, table, key),
        "lookup_string_string_string": lambda table, key, column: _lookup(
            context, table, key, column),
        "date_string": lambda text: dates.parse_date(text, zone),
        "add_hours_timestamp_int": lambda moment, hours: moment + timedelta(hours=hours),
        "add_days_timestamp_int": lambda moment, days: dates.add_days(moment, days, zone),
        "hours_between_timestamp_timestamp": dates.hours_between,
        "days_between_timestamp_timestamp": lambda start, end: dates.days_between(
            start, end, zone),
        "format_date_timestamp_string": lambda moment, pattern: dates.format_date(
            moment, pattern, zone, dict(locale)),
    }
