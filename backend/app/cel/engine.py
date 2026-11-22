"""Template expressions on the server: Google's CEL engine with Skjald's library.

An Engine is made for one set of declared names, such as everything a template can
read (answers.cvss: double, vars.support_phone: string, ...). Checking an
expression runs Skjald's validator (app/cel/lexer.py for the tokens, app/cel/
reader.py for the syntax) and then the engine's own type check, so an expression
that compiles here can't fail on a missing name or a mismatched type when a report
is made. Values are converted by their declared type, the same way the browser
converts them (frontend/src/lib/cel/engine.ts), and a missing value gets the empty
value of its type, so a rule never fails on a blank answer. A row's cells have no
declared type (a repeating group is list<map<string, dyn>>), and there the engine's
Python binding takes numbers, text and yes or no but not a date; so a date in a row is
given as text and the expression reads the rows through a map() that makes it a date
again (_dated below), which is how a date column's cells are dates here as they are
in the browser.

The browser's engine is another one (cel-js), and the two must take the same
expressions and give the same answers. So Skjald reads the syntax itself, by the
same rules on both sides; holds each call to the overloads in shared/cel/
functions.json (the engine's others are refused after its type check, from what
app/cel/checked.py reads of it); and gives the functions the two engines disagree
on itself, under names of its own that an expression is rewritten to.

CEL itself has no loops, no file or network access and no way to run code.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from cel_expr_python import cel
from cel_expr_python.ext import ext_strings

from app.cel import checked, dates
from app.cel.lexer import (
    LexError,
    Token,
    calls,
    declared_prefix,
    paths,
    references,
    tokenize,
)
from app.cel.library import (
    ALIAS,
    ALIASED,
    ALLOWED,
    BANNED,
    ENGINE,
    SIGNATURES,
    Context,
    Table,
    forms,
    implementations,
    regex,
    replacement_parts,
)
from app.cel.reader import RESERVED, TOO_DEEP, Call, Shape, Unreadable, read, unquote

MAX_LENGTH = 2000
DEFAULT_ZONE = "Europe/Copenhagen"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

LOCALES: dict[str, dict[str, Any]] = {
    "en": {
        "months": ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"],
        "short_months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                         "Oct", "Nov", "Dec"],
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                     "Sunday"],
        "decimal": ".",
        "group": ",",
        # Lengths of time in words, one and several: "3 days 1 hour".
        "units": {"day": ["day", "days"], "hour": ["hour", "hours"],
                  "minute": ["minute", "minutes"], "second": ["second", "seconds"]},
    },
    "da": {
        "months": ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august",
                   "september", "oktober", "november", "december"],
        "short_months": ["jan.", "feb.", "mar.", "apr.", "maj", "jun.", "jul.", "aug.",
                         "sep.", "okt.", "nov.", "dec."],
        "weekdays": ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"],
        "decimal": ",",
        "group": ".",
        "units": {"day": ["dag", "dage"], "hour": ["time", "timer"],
                  "minute": ["minut", "minutter"], "second": ["sekund", "sekunder"]},
    },
}

Kind = Literal["invalid", "compile", "runtime"]


class ExpressionError(ValueError):
    """An expression Skjald won't run, or one that failed; the message is fit to show."""

    def __init__(self, kind: Kind, message: str) -> None:
        super().__init__(message)
        self.kind: Kind = kind
        self.message = message


# Types, written as in shared/cel/functions.json: int, list<string>, map<string, dyn>.


@dataclass(frozen=True)
class TypeSpec:
    name: str
    args: tuple[TypeSpec, ...] = ()

    def __str__(self) -> str:
        if not self.args:
            return self.name
        return f"{self.name}<{', '.join(str(a) for a in self.args)}>"


_SCALARS = {"bool", "int", "uint", "double", "string", "bytes", "timestamp", "duration",
            "dyn", "null"}


def parse_type(text: str) -> TypeSpec:
    spec, rest = _parse_type(text.replace(" ", ""))
    if rest:
        raise ValueError(f"Unexpected {rest!r} in the type {text!r}.")
    return spec


def _parse_type(text: str) -> tuple[TypeSpec, str]:
    match = re.match(r"[a-z]+", text)
    if not match:
        raise ValueError(f"Expected a type at {text!r}.")
    name, rest = match.group(0), text[match.end():]
    if name in _SCALARS:
        return TypeSpec(name), rest
    arity = {"list": 1, "map": 2}.get(name)
    if arity is None or not rest.startswith("<"):
        raise ValueError(f"Unknown type {name!r}.")
    args = []
    rest = rest[1:]
    for index in range(arity):
        arg, rest = _parse_type(rest)
        args.append(arg)
        expected = ">" if index == arity - 1 else ","
        if not rest.startswith(expected):
            raise ValueError(f"Expected {expected!r} in a {name} type.")
        rest = rest[1:]
    return TypeSpec(name, tuple(args)), rest


def cel_type(spec: TypeSpec) -> cel.Type:
    T = cel.Type
    if spec.name == "list":
        return T.List(cel_type(spec.args[0]))
    if spec.name == "map":
        return T.Map(cel_type(spec.args[0]), cel_type(spec.args[1]))
    return getattr(T, spec.name.upper())


def type_name(value: cel.Type) -> str:
    """The engine's name for a type (LIST<INT>) the way Skjald writes it (list<int>)."""
    return str(value.name()).lower().replace(",", ", ").replace(",  ", ", ")


def _signature(text: str) -> tuple[str, bool, list[TypeSpec], TypeSpec]:
    """A signature's name, whether it's written after a value and a dot, the types it
    takes (what it's written after first) and what it gives."""
    match = re.fullmatch(r"(?:(.+)\.)?(\w+)\((.*)\):\s*(.+)", text)
    if not match:
        raise ValueError(f"Bad signature {text!r}.")
    receiver, name, params, result = match.groups()
    args: list[TypeSpec] = [parse_type(receiver)] if receiver else []
    depth, current = 0, ""
    for c in params:
        if c == "," and depth == 0:
            args.append(parse_type(current))
            current = ""
            continue
        depth += {"<": 1, ">": -1}.get(c, 0)
        current += c
    if current.strip():
        args.append(parse_type(current))
    return name, receiver is not None, args, parse_type(result)


# Validation

# Names the engines read as types (int on its own is the type, not a value): none is
# a name a template has.
TYPE_WORDS = frozenset({"bool", "bytes", "double", "duration", "dyn", "google", "int", "list",
                        "map", "null_type", "optional_type", "string", "timestamp", "type",
                        "uint"})
FORMS = forms()
# The list functions, with a rule to show how each is written.
LIST_FUNCTIONS = {"exists": "r.attempts > 0", "all": "r.attempts > 0",
                  "exists_one": "r.attempts > 0", "filter": "r.attempts > 0", "map": "r.ip"}
HAS = "has() takes one name with a dot in it, such as has(item.ip) or has(answers.title)."


def unknown_name(name: str) -> str:
    return f"{name.split('.')[0]} isn't a name this template has."


def _values(count: int) -> str:
    return "nothing" if count == 0 else "1 value" if count == 1 else f"{count} values"


def call_problem(call: Call, tokens: list[Token], shape: Shape) -> str | None:
    """What's wrong with how a function is called, before any types are looked at."""
    name = call.name
    if name == "has":
        fits = not call.member and len(call.args) == 1 and call.args[0] in shape.selects
        return None if fits else HAS
    if name in LIST_FUNCTIONS:
        named = False
        if len(call.args) == 2 and call.args[0][1] - call.args[0][0] == 1:
            first = tokens[call.args[0][0]]
            named = first.kind == "ident" and first.text not in RESERVED and first.text not in (
                "true", "false", "null", "in")
        if call.member and named:
            return None
        return (f"{name}() goes after a list, with a name for each item and then a rule: "
                f"answers.rows.{name}(r, {LIST_FUNCTIONS[name]}).")
    counts = FORMS.get((name, call.member))
    if counts is None:
        if call.member:
            return (f"{name}() is written on its own, with its values inside the brackets: "
                    f"{name}(...).")
        return f"{name}() is written after the value it works on: value.{name}(...)."
    if len(call.args) in counts:
        return None
    allowed = sorted(counts)
    takes = _values(allowed[-1]) if len(allowed) == 1 else (
        " or ".join([", ".join(str(n) for n in allowed[:-1]), _values(allowed[-1])]))
    given = "none" if not call.args else str(len(call.args))
    return f"{name}() takes {takes} inside its brackets, not {given}."


_KEY_KINDS = {"text": "text", "number": "a whole number", "bool": "yes or no"}


def _key(tokens: list[Token], start: int, end: int) -> tuple[str, object] | None:
    """A map key that's written out (text, a whole number, true or false), as its value."""
    negative = end - start == 2 and tokens[start].kind == "punct" and tokens[start].text == "-"
    if end - start != 1 and not negative:
        return None
    token = tokens[end - 1]
    if token.kind == "string" and not negative:
        return "text", unquote(token.text)
    if token.kind == "number" and re.fullmatch(r"[0-9]+|0x[0-9a-fA-F]+", token.text):
        value = int(token.text, 16 if token.text.startswith("0x") else 10)
        return "number", -value if negative else value
    if token.kind == "ident" and token.text in ("true", "false") and not negative:
        return "bool", token.text
    return None


def validate(expr: str, declared: Collection[str]) -> list[Token]:
    """What Skjald refuses from the words alone, the same on both sides: functions
    outside the list, matches(), unknown names and a whole group of names as a value.

    An expression can pass this half-written; whether it reads is inspect()'s to say.
    Gives the expression's tokens.
    """
    if len(expr) > MAX_LENGTH:
        raise ExpressionError("invalid", f"Expressions are limited to {MAX_LENGTH:,} characters.")
    try:
        tokens = tokenize(expr)
    except LexError as exc:
        raise ExpressionError("compile", str(exc)) from None
    for call in calls(tokens):
        if call.name in BANNED:
            raise ExpressionError("invalid", BANNED[call.name])
        if call.name not in ALLOWED:
            raise ExpressionError("invalid", f"{call.name}() isn't a function Skjald knows.")
    roots = {name.split(".")[0] for name in declared}
    for path in paths(tokens):
        if declared_prefix(path, declared) is not None:
            continue
        dotted = path.dotted
        inside = sorted(name for name in declared if name.startswith(dotted + "."))
        if inside:
            raise ExpressionError(
                "invalid",
                f"{dotted} on its own isn't a value: use one name inside it, such as {inside[0]}.",
            )
        if len(path.names) > 1 and path.names[0] in roots:
            raise ExpressionError("invalid", f"{dotted} isn't a name this template has.")
    return tokens


def inspect(expr: str, declared: Collection[str]) -> tuple[list[Token], Shape]:
    """Skjald's own checks, the same on both sides; the engine's type check follows.

    After validate(), the syntax is read (app/cel/reader.py) and every call and map
    held to how it may be written. Gives the expression's tokens and its shape.
    """
    tokens = validate(expr, declared)
    for path in paths(tokens):
        if path.names[0] in TYPE_WORDS and declared_prefix(path, declared) is None:
            raise ExpressionError("compile", unknown_name(path.dotted))
    try:
        shape = read(tokens)
    except Unreadable as exc:
        raise ExpressionError(exc.kind, exc.message) from None
    for called in shape.calls:
        problem = call_problem(called, tokens, shape)
        if problem is not None:
            raise ExpressionError("compile", problem)
    for keys in shape.maps:
        # Keys written out are looked at now: one that's there twice makes the map
        # fail on the server and count once in the browser, and one of another kind
        # than the rest can never be found by what the others are found by.
        seen: dict[tuple[str, object], None] = {}
        for start, end in keys:
            key = _key(tokens, start, end)
            if key is None:
                continue
            first = next(iter(seen), key)
            if key[0] != first[0]:
                raise ExpressionError(
                    "compile", "A map's keys must all be the same kind, and this one has "
                               f"{_KEY_KINDS[first[0]]} and {_KEY_KINDS[key[0]]}.")
            if key in seen:
                written = expr[tokens[start].start:tokens[end - 1].end]
                raise ExpressionError(
                    "compile", f"A map has the key {written} twice: each key can be there once.")
            seen[key] = None
    return tokens, shape


def human(type_: str) -> str:
    """A type in words: bool is "yes or no", list<string> "a list"."""
    if type_.startswith("list"):
        return "a list"
    if type_.startswith("map"):
        return "a map"
    return {
        "bool": "yes or no", "string": "text", "int": "a whole number",
        "uint": "a whole number", "double": "a decimal number", "timestamp": "a date and time",
        "google.protobuf.timestamp": "a date and time", "duration": "a length of time",
        "google.protobuf.duration": "a length of time", "null": "nothing", "dyn": "any value",
        "null_type": "nothing",
    }.get(type_.lower(), type_)


def _and(words: list[str]) -> str:
    if len(words) < 2:
        return words[0] if words else "nothing"
    return ", ".join(words[:-1]) + " and " + words[-1]


# The engines word their errors differently; the common ones are said the same way on
# both sides (frontend/src/lib/cel/engine.ts), from the facts each engine gives.
# Google's type checker won't mix whole numbers and decimals; cel-js would, so the
# browser refuses the same comparisons itself.
MIXED_COMPARISON = ("A whole number can't be compared with a decimal: write 9.0 rather than 9, "
                    "or convert one side with double() or int().")
MIXED_ARITHMETIC = ("Whole numbers and decimals can't be mixed in a sum: write 9.0 rather than 9, "
                    "or convert one side with double() or int().")
LOGICAL = "AND (&&) and OR (||) need yes or no on both sides."
NUMBERS = ("int", "uint", "double")


def branches(first: str, second: str) -> str:
    return (f"Both results of an IF / ELSE must be the same kind of value: here "
            f"{human(first)} and {human(second)}.")


def operator_problem(op: str, types: list[str]) -> str:
    """What's wrong with an operator given these types, in Skjald's words."""
    if op in ("&&", "||"):
        return LOGICAL
    if len(types) == 2 and all(t in NUMBERS for t in types) and (
            (types[0] == "double") != (types[1] == "double")):
        return MIXED_ARITHMETIC if op in ("+", "-", "*", "/", "%") else MIXED_COMPARISON
    if len(types) == 1:
        return f"{op} doesn't work with {human(types[0])}."
    return f"{op} doesn't work with {human(types[0])} and {human(types[1])}."


def function_problem(name: str, types: list[str]) -> str:
    return f"{name.removeprefix(ALIAS)}() can't take {_and([human(t) for t in types])}."


LIST_PICK = ("An item of a list is picked by its number, as in answers.rows[0]: to read a name "
             "from every row, use map(), exists(), all() or filter().")


def pick_problem(type_: str) -> str:
    """What's wrong with reading .name or [0] from something that has no parts."""
    if type_.startswith("list"):
        return LIST_PICK
    return (f"Nothing can be picked out of {human(type_)}: only a list, a row or a map has "
            "parts.")


def key_problem(key: str, given: str) -> str:
    return f"This map's items are picked by {human(key)}, not by {human(given)}."


def condition_problem(type_: str) -> str:
    return f"An IF needs yes or no before its question mark, but this is {human(type_)}."


def rule_problem(name: str, type_: str) -> str:
    return f"The rule in {name}() must give yes or no, but this gives {human(type_)}."


def has_problem(type_: str) -> str:
    return f"has() looks for a name in a row or a map, but this is {human(type_)}."


# When the value comes from a row, what it is shows only as the expression runs, and
# there Google's engine doesn't say what it found.
HAS_NEITHER = "has() looks for a name in a row or a map, but this is neither."


def range_problem(type_: str) -> str:
    return (f"exists(), all(), exists_one(), filter() and map() go after a list, but this is "
            f"{human(type_)}.")


def _split_types(text: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for c in text:
        if c == "," and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        depth += {"(": 1, "<": 1, ")": -1, ">": -1}.get(c, 0)
        current += c
    if current.strip():
        parts.append(current.strip())
    return parts


_OVERLOAD = re.compile(r"found no matching overload for '([^']+)' applied to '\((.*)\)'")
_UNDECLARED = re.compile(r"undeclared reference to '([^']+)'")
_SELECT = re.compile(r"expression of type '(.+)' cannot be the operand of a select operation")
_RANGE = re.compile(r"expression of type '(.+)' cannot be the range of a comprehension")
_AT_RUN_TIME = re.compile(r"No matching overloads found : (?:\((.*?)\)\.)?([^(\s]+)\((.*)\)")
# The engine's names for types where they aren't Skjald's.
_TYPES = {"int64": "int", "uint64": "uint", "null_type": "null"}


def _call_message(name: str, types: list[str], asked: bool = False) -> str | None:
    """What a call the engine has no overload for is, in Skjald's words.

    asked: the expression asks has() and has no "in" of its own, so an "in" the
    engine complains of is the one has() was written out as.
    """
    types = [_TYPES.get(t, t) for t in types]
    if name == "@in" and asked and len(types) == 2:
        return has_problem(types[1])
    if name == "_?_:_" and len(types) == 3:
        return branches(types[1], types[2]) if types[0] == "bool" else condition_problem(types[0])
    if name == "_[_]" and len(types) == 2:
        if types[0].startswith("map"):
            return key_problem(types[0][4:].split(",")[0], types[1])
        return pick_problem(types[0])
    if name == "@in":
        return operator_problem("in", types)
    operator = re.fullmatch(r"_(.+)_|(.)_", name)
    if operator:
        return operator_problem(operator.group(1) or operator.group(2), types)
    if re.fullmatch(r"\w+", name):
        return function_problem(name, types)
    return None


def _rule_of(source: str, line: int, column: int) -> str | None:
    """The list function whose rule the engine points at, if it points at one: it
    reports what's wrong with a rule at the function's opening bracket."""
    lines = source.split("\n")
    at = sum(len(text) + 1 for text in lines[:line - 1]) + column - 1
    try:
        tokens = tokenize(source)
    except LexError:
        return None
    for before, token in zip(tokens, tokens[1:], strict=False):
        if token.start == at and token.text == "(" and before.text in LIST_FUNCTIONS:
            return before.text
    return None


def _engine_message(raw: str, source: str = "", asked: bool = False) -> str:
    """The first error the engine reports, in Skjald's words where it's a common one."""
    undeclared = _UNDECLARED.search(raw)
    if undeclared:
        return unknown_name(undeclared.group(1).removeprefix(ALIAS))
    message: str | None = None
    overload = _OVERLOAD.search(raw)
    if overload:
        name, types = overload.group(1), _split_types(overload.group(2))
        where = re.search(r"ERROR: <input>:(\d+):(\d+): ", raw)
        if where and name in ("_?_:_", "_||_", "_&&_") and types:
            # A list function is written out as an IF, an AND or an OR: what's wrong
            # with its rule is said as that, not as the operator nobody wrote.
            function = _rule_of(source, int(where.group(1)), int(where.group(2)))
            if function is not None:
                return rule_problem(function, _TYPES.get(types[0 if name == "_?_:_" else -1],
                                                         types[0 if name == "_?_:_" else -1]))
        message = _call_message(name, types, asked)
        if message is not None:
            return message
    ranged = _RANGE.search(raw)
    if ranged:
        return range_problem(ranged.group(1))
    if asked and "No matching overloads found : @in" in raw:
        return HAS_NEITHER
    late = _AT_RUN_TIME.search(raw)
    if late:  # a value read from a row turned out to be of a kind the function can't take
        receiver, called, given = late.groups()
        message = _call_message(
            called, [*([receiver] if receiver else []), *_split_types(given)], asked)
        if message is not None:
            return message
    select = _SELECT.search(raw)
    if select:
        return pick_problem(select.group(1))
    if "Exceeded max recursion depth" in raw or "Expression recursion limit exceeded" in raw:
        return TOO_DEEP
    found = re.search(r"ERROR: <input>:(\d+):(\d+): ([^\n]*)", raw)
    if found:
        line, column, message = found.groups()
        return f"{message} (line {line}, column {column})"
    message = raw.split("\n")[0]
    message = re.sub(r"^[A-Z_]+: ", "", message)
    quoted = re.fullmatch(r"b'(.*)'", message)
    return quoted.group(1) if quoted else message


# Values


def _empty(spec: TypeSpec) -> Any:
    return {
        "bool": False, "int": 0, "uint": 0, "double": 0.0, "string": "", "bytes": b"",
        "timestamp": EPOCH, "duration": timedelta(0), "list": [], "map": {},
    }.get(spec.name)


def to_cel(value: Any, spec: TypeSpec, name: str) -> Any:
    """A plain value (as JSON would carry it) converted to its declared type."""
    if value is None:
        return _empty(spec)
    wrong = ExpressionError("runtime", f"{name} should be {spec}, not {value!r}.")
    kind = spec.name
    if kind == "bool":
        if not isinstance(value, bool):
            raise wrong
        return value
    if kind in ("int", "uint"):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise wrong
        if isinstance(value, float) and not value.is_integer():
            raise wrong
        return int(value)
    if kind == "double":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise wrong
        return float(value)
    if kind == "string":
        if not isinstance(value, str):
            raise wrong
        return value
    if kind == "timestamp":
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise wrong
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise wrong from None
        if parsed.tzinfo is None:
            raise wrong
        return parsed.astimezone(UTC)
    if kind == "list":
        if not isinstance(value, list):
            raise wrong
        return [to_cel(item, spec.args[0], name) for item in value]
    if kind == "map":
        if not isinstance(value, dict):
            raise wrong
        return {k: to_cel(v, spec.args[1], name) for k, v in value.items()}
    return value


def _find(values: Mapping[str, Any], dotted: str) -> Any:
    current: Any = values
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


# Rows whose cells can be dates: a repeating group's or a table's.
_ROWS = "list<map<string, dyn>>"
_ROW = "skjald_row"
_CELL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
# Names that can't be read after a dot: these cells are read as row["in"].
_WORDS = RESERVED | {"true", "false", "null", "in"}


def _dated(data: dict[str, Any], names: Collection[str]) -> dict[str, str]:
    """Makes rows that hold dates into rows the engine takes, and says how they're read.

    cel-expr-python (0.1.4) converts a Python value by its declared type, and takes a
    datetime only where a timestamp is declared: in a row's cell, which is dyn, it
    refuses one. So each such date becomes text here (in data, in place), and what
    comes back, by declared name, is what a reference to those rows is rewritten to: a
    map() over them that makes every row again, with timestamp() around its dates.
    Inside the engine the cells are then real dates. Reading the rows this way is two
    steps deeper than they were written, three when every column is a date (see
    app/cel/reader.py), so an expression at the very limit of 32 can be too deep here
    when its rows have a date column; it's refused in the same words. Rows that aren't
    all alike (a cell a date in one row and not in another) are left as they are, for
    the engine to refuse.
    """
    found: dict[str, str] = {}
    for name in names:
        rows = data.get(name)
        if not rows:
            continue
        keys = list(rows[0])
        dates = {key for key in keys if isinstance(rows[0][key], datetime)}
        if not dates or not all(isinstance(key, str) and _CELL.match(key) for key in keys):
            continue
        if not all(row.keys() == rows[0].keys()
                   and all(isinstance(row[key], datetime) == (key in dates) for key in keys)
                   for row in rows):
            continue
        for row in rows:
            for key in dates:
                moment = row[key]
                if moment.tzinfo is None:  # as where a timestamp is declared: read as UTC
                    moment = moment.replace(tzinfo=UTC)
                row[key] = moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
        read = {key: f'{_ROW}["{key}"]' if key in _WORDS else f"{_ROW}.{key}" for key in keys}
        cells = {key: f"timestamp({read[key]})" if key in dates else read[key] for key in keys}
        # The engine's checker takes a map's cells to be the kind its first one is, so a
        # cell of no declared kind goes first; where every cell is a date, the first is
        # said to be of any kind with dyn(), which only this writes.
        first = next((key for key in keys if key not in dates), None)
        if first is None:
            first = keys[0]
            cells[first] = f"dyn({cells[first]})"
        written = ", ".join(f'"{key}": {cells[key]}'
                            for key in [first, *(key for key in keys if key != first)])
        found[name] = f"{name}.map({_ROW}, {{{written}}})"
    return found


# What makes each kind of value empty: has(answers.title) is whether the answer is
# anything else, written out for the engine as a comparison.
_FILLED = {
    "string": ' != ""', "int": " != 0", "double": " != 0.0", "bool": " != false",
    "timestamp": ' != timestamp("1970-01-01T00:00:00Z")', "duration": ' != duration("0s")',
    "list": ".size() != 0", "map": ".size() != 0",
}
# to_dyn is dyn(), which no template can call: _dated() writes it into what the engine gets.
_ALLOWED_OVERLOADS = frozenset(SIGNATURES) | frozenset(ENGINE) | {"to_dyn"}
# Google's checker lets nothing (null) stand in for a date or a length of time;
# cel-js doesn't, and a declared date is never nothing, so it's refused here too.
_NEVER_NULL = ("timestamp", "duration")


# Nothing can't be added to or put in order either, though the checker would let it
# stand in for a date there too.
_SUMS_AND_ORDER = frozenset({"_+_", "_-_", "_*_", "_/_", "_%_", "_<_", "_<=_", "_>_", "_>=_", "-_"})


def _null_with(first: str, second: str) -> bool:
    return (first == "null" and second in _NEVER_NULL) or (
        second == "null" and first in _NEVER_NULL)


class Engine:
    """Checks and evaluates expressions over one set of declared names."""

    def __init__(
        self,
        declarations: Mapping[str, str],
        *,
        timezone: str = DEFAULT_ZONE,
        language: str = "en",
        tables: Mapping[str, Table] | None = None,
    ) -> None:
        self.declarations = {name: parse_type(text) for name, text in declarations.items()}
        self._rows = [name for name, spec in self.declarations.items() if str(spec) == _ROWS]
        self._context = Context(ZoneInfo(timezone), LOCALES[language], tables or {})
        impls = implementations(self._context)
        grouped: dict[str, list[cel.Overload]] = {}
        for overload_id, signature in SIGNATURES.items():
            name, member, args, result = _signature(signature)
            grouped.setdefault(ALIAS + name if name in ALIASED else name, []).append(cel.Overload(
                overload_id, cel_type(result), [cel_type(a) for a in args], is_member=member,
                impl=impls[overload_id],
            ))
        self._env = cel.NewEnv(
            variables={name: cel_type(spec) for name, spec in self.declarations.items()},
            extensions=[ext_strings.ExtStrings()],
            functions=[cel.FunctionDecl(name, overloads) for name, overloads in grouped.items()],
        )

    def _literals(self, tokens: list[Token], shape: Shape) -> None:
        """Text written out where a pattern or a date goes is checked now, not each
        time the expression runs."""
        def written(call: Call, index: int) -> str | None:
            if index >= len(call.args) or call.args[index][1] - call.args[index][0] != 1:
                return None
            token = tokens[call.args[index][0]]
            return unquote(token.text) if token.kind == "string" else None

        for call in shape.calls:
            if call.member:
                continue
            if call.name in ("re_match", "re_replace"):
                pattern = written(call, 1)
                if pattern is None:
                    continue
                try:
                    compiled = regex(pattern)
                    replacement = written(call, 2) if call.name == "re_replace" else None
                    if replacement is not None:
                        replacement_parts(replacement, compiled.groups, compiled.groupindex)
                except ValueError as exc:
                    raise ExpressionError("compile", str(exc).replace(
                        "The pattern isn't", f"The pattern in {call.name}() isn't")) from None
            elif call.name in ("date", "format_date"):
                text = written(call, 0 if call.name == "date" else 1)
                if text is None:
                    continue
                try:
                    if call.name == "date":
                        dates.parse_date(text, self._context.zone)
                    else:
                        dates.format_date(EPOCH, text, self._context.zone,
                                          dict(self._context.locale))
                except ValueError as exc:
                    raise ExpressionError("compile", str(exc)) from None

    def _rewritten(self, expr: str, tokens: list[Token], shape: Shape,
                   dated: Mapping[str, str]) -> str:
        """The expression as the engine gets it: has() of a declared name as whether
        it's filled in, has() of anything else as whether the name is in the row (the
        one way of asking that both engines answer alike), Skjald's own int(),
        string() and the like by their names, and rows that hold dates read as
        _dated() says."""
        edits: dict[int, str] = {}
        if dated:
            at = {token.start: index for index, token in enumerate(tokens)}
            for path in paths(tokens):
                name = declared_prefix(path, self.declarations)
                if name is not None and name in dated:
                    first = at[path.start]
                    edits[first] = dated[name]
                    for index in range(first + 1, first + 2 * name.count(".") + 1):
                        edits[index] = ""
        for call in shape.calls:
            if call.name == "has":
                start, end = call.args[0]
                names = tokens[start:end]
                plain = all(t.kind == "ident" if i % 2 == 0 else t.text == "."
                            for i, t in enumerate(names))
                spec = self.declarations.get("".join(t.text for t in names)) if plain else None
                edits[call.at] = ""
                if spec is not None:
                    edits[end] = _FILLED.get(spec.name, " != null") + ")"
                else:
                    edits[call.at + 1] = f'("{tokens[end - 1].text}" in ('
                    edits[end - 2] = ")"
                    edits[end - 1] = ""
            elif call.name in ALIASED:
                edits[call.at] = ALIAS + call.name
        if not edits:
            return expr
        out: list[str] = []
        last = 0
        for index, token in enumerate(tokens):
            out += [expr[last:token.start], edits.get(index, token.text)]
            last = token.end
        return "".join([*out, expr[last:]])

    def _hold(self, compiled: cel.Expression) -> None:
        """Refuses what Google's checker takes and the browser's doesn't."""
        for call in checked.calls(compiled.serialize()):
            types = list(call.types)
            if re.fullmatch(r"\w+", call.function):
                # No function takes nothing (null); Google's checker lets it stand in
                # for a date.
                if "null" in types or (
                        call.overloads and not _ALLOWED_OVERLOADS.intersection(call.overloads)):
                    raise ExpressionError("compile", function_problem(call.function, types))
            elif call.function in ("_==_", "_!=_") and len(types) == 2 and _null_with(*types):
                raise ExpressionError("compile", operator_problem(call.function.strip("_"), types))
            elif call.function in _SUMS_AND_ORDER and "null" in types:
                raise ExpressionError("compile", operator_problem(call.function.strip("_"), types))
            elif call.function == "_?_:_" and len(types) == 3 and _null_with(*types[1:]):
                raise ExpressionError("compile", branches(types[1], types[2]))

    def _compile(self, expr: str, dated: Mapping[str, str] | None = None,
                 ) -> tuple[cel.Expression, bool]:
        """The compiled expression, and whether an "in" in it can only be has()'s.

        dated: rows that hold dates, and what a reference to each is rewritten to.
        """
        tokens, shape = inspect(expr, self.declarations)
        self._literals(tokens, shape)
        source = self._rewritten(expr, tokens, shape, dated or {})
        has = any(call.name == "has" for call in shape.calls)
        if has or source != expr and dated:
            # has() is written out as a comparison in brackets, which can be a step or
            # two deeper than what was written, and rows with dates are read through a
            # map(), which is deeper too; so what the engine gets is read as well.
            try:
                read(tokenize(source))
            except Unreadable as exc:
                raise ExpressionError(exc.kind, exc.message) from None
        asked = has and not any(token.kind == "ident" and token.text == "in" for token in tokens)
        try:
            compiled = self._env.compile(source)
        except RuntimeError as exc:
            raise ExpressionError("compile", _engine_message(str(exc), source, asked)) from None
        self._hold(compiled)
        return compiled, asked

    def check(self, expr: str) -> str:
        """The type the expression gives, if Skjald will run it; else ExpressionError."""
        return type_name(self._compile(expr)[0].return_type())

    def references(self, expr: str) -> list[str]:
        """The declared names the expression reads."""
        return references(validate(expr, self.declarations), self.declarations)

    def evaluate(self, expr: str, values: Mapping[str, Any]) -> Any:
        # An expression that can't be run says so before a value of the wrong kind does.
        wrong: ExpressionError | None = None
        try:
            data = {name: to_cel(_find(values, name), spec, name)
                    for name, spec in self.declarations.items()}
        except ExpressionError as exc:
            data, wrong = {}, exc
        compiled, asked = self._compile(expr, _dated(data, self._rows))
        if wrong is not None:
            raise wrong
        try:
            result = compiled.eval(data=data)
        except Exception as exc:  # the engine's own failures, reported like the rest
            raise ExpressionError("runtime", _engine_message(str(exc), asked=asked)) from None
        if result.type() == cel.Type.ERROR:
            raise ExpressionError(
                "runtime", _engine_message(str(result.value()), asked=asked))
        # The engine's own lists and maps hold wrappers; plain_value gives Python's.
        return cast(Any, result.plain_value())
