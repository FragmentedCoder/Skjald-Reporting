"""Reading an expression's shape from its tokens: Skjald's own check of the syntax.

Both engines parse CEL, but not quite the same CEL: Google's takes a name that starts
with a dot and stops at 32 steps deep, cel-js takes an IF inside an IF without
brackets and whole numbers too large to hold, and each words a syntax error its own
way. So the expression is read here first, by the same rules on both sides (the
browser's copy is frontend/src/lib/cel/reader.ts): what neither or only one engine
would take is refused in Skjald's words, and what's read is the same for both.

What comes back is the expression's shape: every call with where its arguments are,
and every map with where its keys are. The validator (app/cel/engine.py) checks
those against the function list.

How deep the expression goes is counted as it's read, the way Google's parser
counts (cel-expr-python 0.1.4), which is what limits it: it follows 32 steps. Being
inside an expression is a step: the whole expression is the first, and a function's
value, an item of a list or a map, what's between [ and ], an ELSE, a pair of
brackets and what a single ! or - stands before are each one more. So is each
.name, function after a dot, [ ], sum and comparison put on a value, on top of the
deeper of the two it joins. So 32 values can be added in a row, or 17 inside 15
lists; 32 pairs of brackets or 31 functions, lists or ELSE IFs can be inside each
other, but !( only 15 times, being two steps. ANDs and ORs in a row don't count, nor
do !! and --, which Google's parser drops.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.cel.lexer import Token

# Words CEL keeps for itself: none can be a name.
RESERVED = frozenset({
    "as", "break", "const", "continue", "else", "for", "function", "if", "import", "let",
    "loop", "package", "namespace", "return", "var", "void", "while",
})
_LITERALS = ("true", "false", "null")
_RELATIONS = ("<", "<=", ">", ">=", "==", "!=")
_INT = re.compile(r"[0-9]+|0x[0-9a-fA-F]+")
_FLOAT = re.compile(r"(?:[0-9]+\.[0-9]+|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[0-9]+[eE][+-]?[0-9]+")
_ESCAPES = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
            "\\": "\\", "?": "?", '"': '"', "'": "'", "`": "`"}
_HEX = frozenset("0123456789abcdefABCDEF")
MAX_INT = 2**63 - 1

# Google's parser follows an expression 32 steps deep, counted as _Reader counts them;
# cel-js would go further, so the limit is said here for both.
MAX_DEPTH = 32

END = "The expression stops before it's finished."
TOO_DEEP = ("This expression has too many steps in a row or inside each other: split it into "
            "calculated values, or add many numbers up with sum([...]).")


class Unreadable(ValueError):
    """An expression Skjald won't read; the message is fit to show."""

    def __init__(self, kind: Literal["invalid", "compile"], message: str) -> None:
        super().__init__(message)
        self.kind: Literal["invalid", "compile"] = kind
        self.message = message


@dataclass(frozen=True)
class Call:
    name: str
    # Written after a value and a dot, as in answers.title.size().
    member: bool
    # Where the name is among the tokens, and where each argument starts and ends.
    at: int
    args: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Shape:
    calls: tuple[Call, ...]
    # Each map's keys: where each starts and ends among the tokens.
    maps: tuple[tuple[tuple[int, int], ...], ...]
    # Runs of tokens that are a value, a dot and a name, and nothing more.
    selects: frozenset[tuple[int, int]]


def unquote(text: str) -> str | None:
    """The text a text literal stands for; None if it has an escape CEL doesn't know."""
    start = 1 if text[0] in "rR" else 0
    raw = start == 1
    quote = text[start] * 3 if text.startswith(text[start] * 3, start) else text[start]
    body = text[start + len(quote):len(text) - len(quote)]
    if raw:
        # Google's engine won't have a raw text end in a backslash.
        return None if (len(body) - len(body.rstrip("\\"))) % 2 else body
    out: list[str] = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        code = body[i + 1:i + 2]
        if code in _ESCAPES:
            out.append(_ESCAPES[code])
            i += 2
            continue
        width = {"x": 2, "X": 2, "u": 4, "U": 8}.get(code)
        if width is not None:
            digits = body[i + 2:i + 2 + width]
            i += 2 + width
        elif code and code in "0123":
            digits = body[i + 1:i + 4]
            i += 4
            if len(digits) != 3 or not set(digits[1:]) <= set("01234567"):
                return None
            out.append(chr(int(digits, 8)))
            continue
        else:
            return None
        if len(digits) != width or not set(digits) <= _HEX:
            return None
        value = int(digits, 16)
        if value > 0x10FFFF or 0xD800 <= value <= 0xDFFF:
            return None
        out.append(chr(value))
    return "".join(out)


class _Reader:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.i = 0
        # Depth is counted as Google's parser counts it, in steps of two kinds that
        # add up. One is how many expressions this place is inside of: the whole
        # expression is one, and a pair of brackets, a function's value, an item of a
        # list or a map, what's between [ and ], an ELSE and what a single ! or -
        # stands before are each one more. The other is how many steps the value read
        # goes itself, which is what each reading gives back: nothing for a name or a
        # value written out, one for each .name, function after a dot, [ ], sum and
        # comparison on top of the deeper of what it joins. Brackets, a function
        # before its brackets, a list and a map go as deep as what's in them; an IF as
        # deep as its ELSE; ANDs and ORs don't count and start again from nothing.
        self.inside = 0
        self.calls: list[Call] = []
        self.maps: list[tuple[tuple[int, int], ...]] = []
        self.selects: set[tuple[int, int]] = set()

    def punct(self, *texts: str) -> bool:
        if self.i >= len(self.tokens):
            return False
        token = self.tokens[self.i]
        return token.kind == "punct" and token.text in texts

    def word(self, text: str) -> bool:
        if self.i >= len(self.tokens):
            return False
        token = self.tokens[self.i]
        return token.kind == "ident" and token.text == text

    def unexpected(self) -> Unreadable:
        if self.i >= len(self.tokens):
            return Unreadable("compile", END)
        token = self.tokens[self.i]
        text = token.text if len(token.text) <= 20 else token.text[:20] + "…"
        return Unreadable("compile", f"Unexpected '{text}' at position {token.start + 1}.")

    def expect(self, text: str) -> None:
        if not self.punct(text):
            raise self.unexpected()
        self.i += 1

    def fits(self, steps: int) -> None:
        """Refuses what Google's parser wouldn't follow: one more step on a value that
        goes this many already, or this many more expressions to be inside of."""
        if self.inside + steps > MAX_DEPTH:
            raise Unreadable("invalid", TOO_DEEP)

    def expr(self) -> int:
        self.fits(1)
        self.inside += 1
        height = self.conditional()
        self.inside -= 1
        return height

    def conditional(self, left: tuple[int, int] | None = None) -> int:
        """An expression where it's already counted as one to be inside of. left: a
        value in brackets that's been read and that this carries on from, as where
        it starts and how deep it goes."""
        height = self.either(left)
        if self.punct("?"):
            self.i += 1
            self.either()
            if self.punct("?"):
                raise Unreadable(
                    "compile", "An IF inside the first result of another IF needs brackets around "
                               f"it (position {self.tokens[self.i].start + 1}).")
            self.expect(":")
            height = self.expr()
        return height

    def either(self, left: tuple[int, int] | None = None) -> int:
        height = self.both(left)
        if not self.punct("||"):
            return height
        while self.punct("||"):
            self.i += 1
            self.both()
        return 0

    def both(self, left: tuple[int, int] | None = None) -> int:
        height = self.relation(left)
        if not self.punct("&&"):
            return height
        while self.punct("&&"):
            self.i += 1
            self.relation()
        return 0

    def relation(self, left: tuple[int, int] | None = None) -> int:
        height = self.sum(left)
        while self.punct(*_RELATIONS) or self.word("in"):
            self.i += 1
            self.fits(height)
            height = 1 + max(height, self.sum())
        return height

    def sum(self, left: tuple[int, int] | None = None) -> int:
        height = self.product(left)
        while self.punct("+", "-"):
            self.i += 1
            self.fits(height)
            height = 1 + max(height, self.product())
        return height

    def product(self, left: tuple[int, int] | None = None) -> int:
        height = self.unary(left)
        while self.punct("*", "/", "%"):
            self.i += 1
            self.fits(height)
            height = 1 + max(height, self.unary())
        return height

    def number_follows(self) -> bool:
        return self.i + 1 < len(self.tokens) and self.tokens[self.i + 1].kind == "number"

    def unary(self, left: tuple[int, int] | None = None) -> int:
        if left is not None:
            return self.member(left)
        for sign in ("!", "-"):
            if self.punct(sign) and not (sign == "-" and self.number_follows()):
                # Google's parser drops them in pairs: of !!!x one is left, of !!x none.
                kept = 0
                while self.punct(sign):
                    self.i += 1
                    kept = 1 - kept
                if kept:
                    self.fits(0)
                self.inside += kept
                height = self.member()
                self.inside -= kept
                return height
        return self.member()

    def member(self, left: tuple[int, int] | None = None) -> int:
        start, height = left if left is not None else (self.i, self.primary())
        while True:
            if self.punct("."):
                self.fits(height)
                self.i += 1
                if self.i >= len(self.tokens):
                    raise self.unexpected()
                name = self.tokens[self.i]
                if name.kind != "ident" or name.text in _LITERALS or name.text == "in":
                    raise self.unexpected()
                self.i += 1
                if self.punct("("):
                    heights = self.arguments(name.text, True, self.i - 1)
                    height = 1 + max([height, *heights])
                else:
                    height += 1
                    self.selects.add((start, self.i))
            elif self.punct("["):
                self.fits(height)
                self.i += 1
                height = 1 + max(height, self.expr())
                self.expect("]")
            else:
                return height

    def arguments(self, name: str, member: bool, at: int) -> list[int]:
        self.expect("(")
        heights: list[int] = []
        ranges: list[tuple[int, int]] = []
        if not self.punct(")"):
            while True:
                start = self.i
                heights.append(self.expr())
                ranges.append((start, self.i))
                if not self.punct(","):
                    break
                self.i += 1
        self.expect(")")
        self.calls.append(Call(name, member, at, tuple(ranges)))
        return heights

    def primary(self) -> int:
        if self.i >= len(self.tokens):
            raise self.unexpected()
        token = self.tokens[self.i]
        if token.kind == "number" or (self.punct("-") and self.number_follows()):
            negative = token.kind != "number"
            self.i += 1 if negative else 0
            self.number(self.tokens[self.i], negative)
            self.i += 1
            return 0
        if token.kind == "string":
            self.text(token)
            self.i += 1
            return 0
        if token.kind == "punct":
            if token.text == "(":
                # Google's parser takes brackets right inside brackets in one go: the
                # run of them must fit, and what's in them is inside one expression
                # more, not one for each pair.
                opened = []
                while self.punct("("):
                    opened.append(self.i)
                    self.i += 1
                self.fits(len(opened) - 1)
                self.inside += 1
                height = self.conditional()
                for pair in reversed(opened):
                    self.expect(")")
                    if pair != opened[0] and not self.punct(")"):
                        height = self.conditional((pair, height))
                self.inside -= 1
                return height
            if token.text == "[":
                self.i += 1
                heights = [0]
                while not self.punct("]"):
                    heights.append(self.expr())
                    if not self.punct(","):
                        break
                    self.i += 1
                self.expect("]")
                return max(heights)
            if token.text == "{":
                self.i += 1
                heights = [0]
                keys: list[tuple[int, int]] = []
                while not self.punct("}"):
                    start = self.i
                    heights.append(self.expr())
                    keys.append((start, self.i))
                    self.expect(":")
                    heights.append(self.expr())
                    if not self.punct(","):
                        break
                    self.i += 1
                self.expect("}")
                self.maps.append(tuple(keys))
                return max(heights)
            if token.text == ".":
                raise Unreadable(
                    "invalid", f"A name can't start with a dot (position {token.start + 1}).")
            raise self.unexpected()
        if token.text in _LITERALS:
            self.i += 1
            return 0
        if token.text == "in":
            raise self.unexpected()
        self.i += 1
        if self.punct("("):
            return max([0, *self.arguments(token.text, False, self.i - 1)])
        if token.text in RESERVED:
            raise Unreadable("compile", f"{token.text} is a reserved word in expressions.")
        return 0

    def number(self, token: Token, negative: bool) -> None:
        text = token.text
        if text[-1] in "uU" and _INT.fullmatch(text[:-1]):
            raise Unreadable("invalid", f"Whole numbers are written without a u: {text[:-1]} "
                                        f"rather than {text}.")
        if _INT.fullmatch(text):
            if int(text, 0 if text.startswith("0x") else 10) > MAX_INT + (1 if negative else 0):
                raise Unreadable("compile", f"{text} is too large for a whole number.")
        elif not _FLOAT.fullmatch(text):
            raise Unreadable("compile", f"{text} isn't a number Skjald can read "
                                        f"(position {token.start + 1}).")
        elif float(text) == float("inf"):
            raise Unreadable("compile", f"{text} is too large for a number.")

    def text(self, token: Token) -> None:
        prefix = token.text[:len(token.text) - len(token.text.lstrip("rRbB"))]
        if "b" in prefix.lower():
            raise Unreadable("invalid", "Text is written without a b before the quote "
                                        f"(position {token.start + 1}).")
        if unquote(token.text) is None:
            raise Unreadable(
                "compile", f"The text at position {token.start + 1} has a backslash Skjald can't "
                           "read: write \\\\ for a backslash itself.")


def read(tokens: list[Token]) -> Shape:
    """The expression's shape, if it's one both engines read the same way."""
    reader = _Reader(tokens)
    reader.expr()
    if reader.i < len(tokens):
        raise reader.unexpected()
    return Shape(tuple(reader.calls), tuple(reader.maps), frozenset(reader.selects))
