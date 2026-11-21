"""Skjald's function library on the server: what templates may call, and the
functions Skjald adds to Google's CEL engine.

shared/cel/functions.json is the list both engines follow; a test holds these
declarations to it. The browser's copy is frontend/src/lib/cel/library.ts.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
    "int_string": "int(string): int",
    "int_double": "int(double): int",
    "int_int": "int(int): int",
    "double_string": "double(string): double",
    "double_int": "double(int): double",
    "double_double": "double(double): double",
    "string_int": "string(int): string",
    "string_double": "string(double): string",
    "string_bool": "string(bool): string",
    "string_string": "string(string): string",
    "substring_int_int": "string.substring(int, int): string",
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


# The overloads Google's engine brings that templates may use, by the engine's own ID
# for each (the list functions and has() are written out by its parser and have none,
# so theirs are Skjald's names). A call the engine resolves to any other overload,
# such as string() of a date or replace() with a count, is refused: the browser's
# engine doesn't have them, and the two must take the same expressions.
ENGINE: dict[str, str] = {
    "string_replace_string_string": "string.replace(string, string): string",
    "string_size": "string.size(): int",
    "list_size": "list<dyn>.size(): int",
    "map_size": "map<dyn, dyn>.size(): int",
    "size_string": "size(string): int",
    "size_list": "size(list<dyn>): int",
    "size_map": "size(map<dyn, dyn>): int",
    "contains_string": "string.contains(string): bool",
    "starts_with_string": "string.startsWith(string): bool",
    "ends_with_string": "string.endsWith(string): bool",
    "string_upper_ascii": "string.upperAscii(): string",
    "string_lower_ascii": "string.lowerAscii(): string",
    "string_trim": "string.trim(): string",
    "string_split_string": "string.split(string): list<string>",
    "list_join_string": "list<string>.join(string): string",
    "string_index_of_string": "string.indexOf(string): int",
    "has_macro": "has(dyn): bool",
    "exists_macro": "list<dyn>.exists(name, bool): bool",
    "all_macro": "list<dyn>.all(name, bool): bool",
    "exists_one_macro": "list<dyn>.exists_one(name, bool): bool",
    "filter_macro": "list<dyn>.filter(name, bool): list<dyn>",
    "map_macro": "list<dyn>.map(name, dyn): list<dyn>",
    "string_to_timestamp": "timestamp(string): timestamp",
    "int64_to_timestamp": "timestamp(int): timestamp",
    "string_to_duration": "duration(string): duration",
}

# Functions Skjald gives under a name of its own, because the engine has one by that
# name that doesn't do what the browser's does: its int(" 42 ") is 42, its
# string(1000000.0) is 1e+06, and its substring() fails when it ends where the text
# does. An expression's int(...) is rewritten to skjald_int(...) before the engine
# sees it (app/cel/engine.py), and back in what's said about it.
ALIAS = "skjald_"
ALIASED = frozenset({"int", "double", "string", "substring"})

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MAX_INT = 2**63 - 1
PATTERN = "The pattern isn't a regular expression Skjald can use (RE2 syntax)."


def forms() -> dict[tuple[str, bool], set[int]]:
    """How each function is written: by name and whether it comes after a value and a
    dot, how many values go inside its brackets."""
    found: dict[tuple[str, bool], set[int]] = {}
    for signature in (*SIGNATURES.values(), *ENGINE.values()):
        match = re.fullmatch(r"(?:(.+)\.)?(\w+)\((.*)\):\s*.+", signature)
        if not match:
            raise ValueError(f"Bad signature {signature!r}.")
        receiver, name, params = match.groups()
        depth = count = 0
        for c in params:
            depth += {"<": 1, ">": -1}.get(c, 0)
            count += c == "," and depth == 0
        found.setdefault((name, receiver is not None), set()).add(
            count + 1 if params.strip() else 0)
    return found


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


def _only_on_the_server(pattern: str) -> bool:
    """Whether a pattern RE2 takes uses what the browser's RE2 doesn't: \\C (one byte,
    which could cut a letter in two) or one group name twice."""
    names: set[str] = set()
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            code = pattern[i + 1:i + 2]
            if code == "C":
                return True
            if code == "Q":  # everything up to \E is plain text
                end = pattern.find("\\E", i + 2)
                i = len(pattern) if end < 0 else end
            i += 2
        elif c == "[":  # a set of characters: nothing in it is a group
            i += 2 if pattern.startswith("[^", i) else 1
            i += pattern.startswith("]", i)
            while i < len(pattern) and pattern[i] != "]":
                if pattern.startswith("[:", i):
                    end = pattern.find(":]", i + 2)
                    i = i + 1 if end < 0 else end + 1
                i += 2 if pattern[i] == "\\" else 1
            i += 1
        elif c == "(" and (named := re.match(r"\(\?P?<(\w+)>", pattern[i:])):
            if named.group(1) in names:
                return True
            names.add(named.group(1))
            i += named.end()
        else:
            i += 1
    return False


@lru_cache(maxsize=256)
def regex(pattern: str) -> Any:
    """A regular expression both sides can use: RE2's syntax, less what only one has."""
    options = re2.Options()
    options.log_errors = False
    try:
        compiled = re2.compile(pattern, options)
    except Exception:
        raise ValueError(PATTERN) from None
    if _only_on_the_server(pattern):
        raise ValueError(PATTERN)
    return compiled


def replacement_parts(replacement: str, groups: int, names: Mapping[str, int]) -> list[str | int]:
    """Skjald's replacement text as plain text and group numbers: $1 or ${1} is a
    group by number, ${name} one by name, $0 the whole match and $$ a dollar sign."""
    parts: list[str | int] = []
    i = 0
    while i < len(replacement):
        c = replacement[i]
        written: str | None = None
        if c != "$":
            parts.append(c)
        elif replacement.startswith("$$", i):
            parts.append("$")
            i += 1
        elif replacement.startswith("${", i) and "}" in replacement[i:]:
            end = replacement.index("}", i)
            written = replacement[i + 2:end]
            i = end
        elif replacement[i + 1:i + 2].isascii() and replacement[i + 1:i + 2].isdigit():
            j = i + 1
            while j < len(replacement) and replacement[j].isascii() and replacement[j].isdigit():
                j += 1
            written = replacement[i + 1:j]
            i = j - 1
        else:
            parts.append("$")
        if written is not None:
            numbered = written.isascii() and written.isdigit()
            group = int(written) if numbered else names.get(written, -1)
            if not 0 <= group <= groups:
                shown = f"${written}" if numbered and replacement[i] != "}" else f"${{{written}}}"
                raise ValueError(f"The replacement uses {shown}, a group the pattern doesn't have.")
            parts.append(group)
        i += 1
    return parts


def _re_replace(text: str, pattern: str, replacement: str) -> str:
    compiled = regex(pattern)
    parts = replacement_parts(replacement, compiled.groups, compiled.groupindex)
    return str(compiled.sub(
        lambda found: "".join(part if isinstance(part, str) else found.group(part) or ""
                              for part in parts), text))


SUM_NUMBERS = "sum() adds numbers up, and this list holds something that isn't one."
TOO_LARGE = "The result is too large for a whole number."


def _sum(items: list[Any]) -> int | float:
    """The total; an item that's nothing (a blank cell) adds nothing."""
    numbers = [x for x in items if x is not None]
    if any(isinstance(x, bool) or not isinstance(x, int | float) for x in numbers):
        raise ValueError(SUM_NUMBERS)
    if all(isinstance(x, int) for x in numbers):
        whole = sum(numbers)
        if not -MAX_INT - 1 <= whole <= MAX_INT:
            raise ValueError(TOO_LARGE)
        return int(whole)
    total = 0.0
    for x in numbers:
        total += float(x)
    return total


def _int_from_text(text: str) -> int:
    if not re.fullmatch(r"[+-]?[0-9]+", text, re.ASCII):
        raise ValueError(f"int() can't read '{text}' as a whole number.")
    value = int(text)
    if not -MAX_INT - 1 <= value <= MAX_INT:
        raise ValueError(TOO_LARGE)
    return value


def _int_from_double(value: float) -> int:
    if not math.isfinite(value) or not -2.0**63 < value < 2.0**63:
        raise ValueError(TOO_LARGE)
    return int(value)


def _double_from_text(text: str) -> float:
    if not re.fullmatch(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text, re.ASCII):
        raise ValueError(f"double() can't read '{text}' as a number.")
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"double() can't read '{text}' as a number.")
    return value


SUBSTRING = ("substring() takes two positions from 0 to the length of the text, the first no "
             "larger than the second.")


def _substring(text: str, start: int, end: int) -> str:
    if not 0 <= start <= end <= len(text):
        raise ValueError(SUBSTRING)
    return text[start:end]


def _text_from_double(value: float) -> str:
    """A decimal as it's written, never with an exponent: 1234567.5, 0.0000001."""
    if not math.isfinite(value):
        raise ValueError("string() needs a finite number.")
    if value == 0:
        return "0"
    text = format(Decimal(repr(value)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


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

    def format_date(moment: datetime, pattern: str) -> str:
        # The pattern is read even for the empty date, so a wrong one is still said.
        text = dates.format_date(moment, pattern, zone, dict(locale))
        return "" if moment == EPOCH else text

    return {
        "xor_bool_bool": lambda a, b: a != b,
        "switch_string_string": lambda v, cases, default: cases.get(v, default),
        "switch_int_string": lambda v, cases, default: cases.get(v, default),
        "switch_string_double": lambda v, cases, default: cases.get(v, default),
        "switch_string_int": lambda v, cases, default: cases.get(v, default),
        "int_string": _int_from_text,
        "int_double": _int_from_double,
        "int_int": lambda value: value,
        "double_string": _double_from_text,
        "double_int": float,
        "double_double": lambda value: value,
        "string_int": str,
        "string_double": _text_from_double,
        "string_bool": lambda value: "true" if value else "false",
        "string_string": lambda value: value,
        "substring_int_int": _substring,
        "re_match_string_string": lambda text, pattern: regex(pattern).search(text) is not None,
        "re_replace_string_string_string": _re_replace,
        "format_number_double_int": lambda value, places: numbers.format_number(
            value, places, locale["decimal"], locale["group"]),
        "format_number_int_int": lambda value, places: numbers.format_number(
            value, places, locale["decimal"], locale["group"]),
        "sum_list": _sum,
        "lookup_string_string": lambda table, key: _lookup(context, table, key),
        "lookup_string_string_string": lambda table, key, column: _lookup(
            context, table, key, column),
        "date_string": lambda text: dates.parse_date(text, zone),
        # A date that isn't answered is the empty date, and stays it: no days or
        # hours are added to it, and it's written as no text at all.
        "add_hours_timestamp_int": lambda moment, hours: (
            moment if moment == EPOCH else moment + timedelta(hours=hours)),
        "add_days_timestamp_int": lambda moment, days: (
            moment if moment == EPOCH else dates.add_days(moment, days, zone)),
        "hours_between_timestamp_timestamp": dates.hours_between,
        "days_between_timestamp_timestamp": lambda start, end: dates.days_between(
            start, end, zone),
        "format_date_timestamp_string": format_date,
    }
