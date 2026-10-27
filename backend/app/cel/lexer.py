"""A tokenizer for CEL, and what Skjald reads from the tokens.

Skjald's validator works on tokens rather than on either engine's syntax tree, so
the server and the browser (frontend/src/lib/cel/lexer.ts, the same rules) refuse
the same expressions with the same words: functions outside the shared list,
matches(), and a whole group of names used as a value. The tokens also say which
declared names an expression reads, for the order calculated values are worked
out in and for what each question is used by.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from dataclasses import dataclass
from typing import Literal

Kind = Literal["ident", "number", "string", "punct"]

_PUNCT2 = ("==", "!=", "<=", ">=", "&&", "||")
_PUNCT1 = "<>+-*/%!?:.,[]{}()"
_IDENT_START = frozenset("_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_IDENT_PART = _IDENT_START | frozenset("0123456789")
_DIGITS = frozenset("0123456789")
_HEX = _DIGITS | frozenset("abcdefABCDEF")
_SPACE = frozenset(" \t\n\r\f")


class LexError(ValueError):
    """The expression can't be split into tokens; the message is fit to show."""


@dataclass(frozen=True)
class Token:
    kind: Kind
    text: str
    start: int
    end: int


def tokenize(expr: str) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(expr)
    while i < n:
        c = expr[i]
        if c in _SPACE:
            i += 1
        elif expr.startswith("//", i):
            end = expr.find("\n", i)
            i = n if end < 0 else end
        elif _starts_string(expr, i):
            end = _string_end(expr, i)
            tokens.append(Token("string", expr[i:end], i, end))
            i = end
        elif c in _IDENT_START:
            end = i + 1
            while end < n and expr[end] in _IDENT_PART:
                end += 1
            tokens.append(Token("ident", expr[i:end], i, end))
            i = end
        elif c in _DIGITS or (c == "." and i + 1 < n and expr[i + 1] in _DIGITS):
            end = _number_end(expr, i)
            tokens.append(Token("number", expr[i:end], i, end))
            i = end
        elif expr[i:i + 2] in _PUNCT2:
            tokens.append(Token("punct", expr[i:i + 2], i, i + 2))
            i += 2
        elif c in _PUNCT1:
            tokens.append(Token("punct", c, i, i + 1))
            i += 1
        else:
            raise LexError(f"Unexpected character {c!r} at position {i + 1}.")
    return tokens


def _prefix_length(expr: str, i: int) -> int:
    """Length of a string prefix (r, b, rb, br in either case) at i, if a quote follows."""
    for length in (2, 1):
        prefix = expr[i:i + length].lower()
        valid = prefix in ("r", "b") if length == 1 else prefix in ("rb", "br")
        if valid and expr[i + length:i + length + 1] in ("'", '"'):
            return length
    return 0


def _starts_string(expr: str, i: int) -> bool:
    return expr[i] in ("'", '"') or _prefix_length(expr, i) > 0


def _string_end(expr: str, i: int) -> int:
    prefix = _prefix_length(expr, i)
    raw = "r" in expr[i:i + prefix].lower()
    j = i + prefix
    quote = expr[j] * 3 if expr.startswith(expr[j] * 3, j) else expr[j]
    j += len(quote)
    while j < len(expr):
        if not raw and expr[j] == "\\":
            j += 2
            continue
        if expr.startswith(quote, j):
            return j + len(quote)
        if len(quote) == 1 and expr[j] == "\n":
            break
        j += 1
    raise LexError(f"Text starting at position {i + 1} has no closing quote.")


def _number_end(expr: str, i: int) -> int:
    n = len(expr)
    if expr.startswith(("0x", "0X"), i):
        j = i + 2
        while j < n and expr[j] in _HEX:
            j += 1
        return j + 1 if j < n and expr[j] in "uU" else j
    j = i
    while j < n and expr[j] in _DIGITS:
        j += 1
    decimal = False
    if j < n and expr[j] == "." and j + 1 < n and expr[j + 1] in _DIGITS:
        decimal = True
        j += 1
        while j < n and expr[j] in _DIGITS:
            j += 1
    if j < n and expr[j] in "eE":
        k = j + 1
        if k < n and expr[k] in "+-":
            k += 1
        if k < n and expr[k] in _DIGITS:
            decimal = True
            j = k
            while j < n and expr[j] in _DIGITS:
                j += 1
    if not decimal and j < n and expr[j] in "uU":
        j += 1
    return j


@dataclass(frozen=True)
class Call:
    name: str
    member: bool
    start: int


def calls(tokens: list[Token]) -> Iterator[Call]:
    """Every function or macro called: a name followed by an opening bracket."""
    for index, token in enumerate(tokens):
        if token.kind != "ident" or index + 1 >= len(tokens):
            continue
        if tokens[index + 1].text == "(":
            member = index > 0 and tokens[index - 1].text == "."
            yield Call(token.text, member, token.start)


@dataclass(frozen=True)
class Path:
    """A run of names joined by dots, such as answers.cvss; never a function's name."""

    names: tuple[str, ...]
    start: int
    end: int

    @property
    def dotted(self) -> str:
        return ".".join(self.names)


def paths(tokens: list[Token]) -> Iterator[Path]:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        after_dot = index > 0 and tokens[index - 1].text == "."
        is_call = index + 1 < len(tokens) and tokens[index + 1].text == "("
        if token.kind != "ident" or after_dot or is_call:
            index += 1
            continue
        names = [token.text]
        end = token.end
        index += 1
        while (
            index + 1 < len(tokens)
            and tokens[index].text == "."
            and tokens[index + 1].kind == "ident"
            and not (index + 2 < len(tokens) and tokens[index + 2].text == "(")
        ):
            names.append(tokens[index + 1].text)
            end = tokens[index + 1].end
            index += 2
        yield Path(tuple(names), token.start, end)


def declared_prefix(path: Path, declared: Collection[str]) -> str | None:
    """The longest part of the path that is a declared name."""
    for length in range(len(path.names), 0, -1):
        candidate = ".".join(path.names[:length])
        if candidate in declared:
            return candidate
    return None


def references(tokens: list[Token], declared: Collection[str]) -> list[str]:
    """The declared names an expression reads, sorted."""
    found = {declared_prefix(path, declared) for path in paths(tokens)}
    return sorted(name for name in found if name is not None)
