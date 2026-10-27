"""Template expressions on the server: Google's CEL engine with Skjald's library.

An Engine is made for one set of declared names, such as everything a template can
read (answers.cvss: double, vars.support_phone: string, ...). Checking an
expression runs Skjald's validator (app/cel/lexer.py) and then the engine's own
type check, so an expression that compiles here can't fail on a missing name or a
mismatched type when a report is made. Values are converted by their declared
type, the same way the browser converts them (frontend/src/lib/cel/engine.ts), and
a missing value gets the empty value of its type, so a rule never fails on a blank
answer.

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

from app.cel.lexer import (
    LexError,
    Token,
    calls,
    declared_prefix,
    paths,
    references,
    tokenize,
)
from app.cel.library import ALLOWED, BANNED, SIGNATURES, Context, Table, implementations

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
    },
    "da": {
        "months": ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august",
                   "september", "oktober", "november", "december"],
        "short_months": ["jan.", "feb.", "mar.", "apr.", "maj", "jun.", "jul.", "aug.",
                         "sep.", "okt.", "nov.", "dec."],
        "weekdays": ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"],
        "decimal": ",",
        "group": ".",
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


def _signature(text: str) -> tuple[str, list[TypeSpec], TypeSpec]:
    match = re.fullmatch(r"(\w+)\((.*)\):\s*(.+)", text)
    if not match:
        raise ValueError(f"Bad signature {text!r}.")
    name, params, result = match.groups()
    args: list[TypeSpec] = []
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
    return name, args, parse_type(result)


# Validation


def validate(expr: str, declared: Collection[str]) -> list[Token]:
    """Skjald's own checks, the same on both sides; the engine's type check follows."""
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


# Google's type checker won't mix whole numbers and decimals; cel-js would, so the
# browser refuses the same comparisons itself. Both sides say it the same way.
MIXED_COMPARISON = ("A whole number can't be compared with a decimal: write 9.0 rather than 9, "
                    "or convert one side with double() or int().")
MIXED_ARITHMETIC = ("Whole numbers and decimals can't be mixed in a sum: write 9.0 rather than 9, "
                    "or convert one side with double() or int().")
_MIXED = re.compile(
    r"found no matching overload for '_(==|!=|<|<=|>|>=|\+|-|\*|/|%)_' applied to "
    r"'\((int|uint|double), (int|uint|double)\)'"
)


def _engine_message(raw: str) -> str:
    """The first error the engine reports, without its codes and source excerpt."""
    mixed = _MIXED.search(raw)
    if mixed and (mixed.group(2) == "double") != (mixed.group(3) == "double"):
        return MIXED_ARITHMETIC if mixed.group(1) in "+-*/%" else MIXED_COMPARISON
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


def plain(value: Any) -> Any:
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {plain(k): plain(v) for k, v in value.items()}
    return value


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
        context = Context(ZoneInfo(timezone), LOCALES[language], tables or {})
        impls = implementations(context)
        grouped: dict[str, list[cel.Overload]] = {}
        for overload_id, signature in SIGNATURES.items():
            name, args, result = _signature(signature)
            grouped.setdefault(name, []).append(cel.Overload(
                overload_id, cel_type(result), [cel_type(a) for a in args],
                impl=impls[overload_id],
            ))
        self._env = cel.NewEnv(
            variables={name: cel_type(spec) for name, spec in self.declarations.items()},
            extensions=[ext_strings.ExtStrings()],
            functions=[cel.FunctionDecl(name, overloads) for name, overloads in grouped.items()],
        )

    def _compile(self, expr: str) -> cel.Expression:
        validate(expr, self.declarations)
        try:
            return self._env.compile(expr)
        except RuntimeError as exc:
            raise ExpressionError("compile", _engine_message(str(exc))) from None

    def check(self, expr: str) -> str:
        """The type the expression gives, if Skjald will run it; else ExpressionError."""
        return type_name(self._compile(expr).return_type())

    def references(self, expr: str) -> list[str]:
        """The declared names the expression reads."""
        return references(validate(expr, self.declarations), self.declarations)

    def evaluate(self, expr: str, values: Mapping[str, Any]) -> Any:
        compiled = self._compile(expr)
        data = {name: to_cel(_find(values, name), spec, name)
                for name, spec in self.declarations.items()}
        try:
            result = compiled.eval(data=data)
        except Exception as exc:  # the engine's own failures, reported like the rest
            raise ExpressionError("runtime", _engine_message(str(exc))) from None
        if result.type() == cel.Type.ERROR:
            raise ExpressionError("runtime", _engine_message(str(result.value())))
        return plain(cast(Any, result.value()))
