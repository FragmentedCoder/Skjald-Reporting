"""What Google's type checker decided about an expression, read from its serialized form.

cel-expr-python compiles and checks an expression but doesn't show the checked
syntax tree. It can write it out, though, as a cel.expr.CheckedExpr message, and
that holds what Skjald needs to keep the server to the same functions as the
browser: which overload each call was resolved to, and the type of every argument.

The message is read here with a few lines of protobuf wire format rather than a
protobuf library (the engine doesn't bring one): only varints and length-prefixed
fields occur, and the field numbers are those of cel/expr/checked.proto and
syntax.proto, which are a published, frozen format. A test holds this reader to
what the engine writes (backend/tests/test_cel.py).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

_PRIMITIVES = {1: "bool", 2: "int", 3: "uint", 4: "double", 5: "string", 6: "bytes"}
_WELL_KNOWN = {1: "dyn", 2: "timestamp", 3: "duration"}


@dataclass(frozen=True)
class Call:
    """One call in the checked tree: a function or an operator (_+_, _==_, _?_:_)."""

    function: str
    # The overloads the checker kept; several when an argument's type isn't known.
    overloads: tuple[str, ...]
    # The types of what it's called on, if anything, and of its arguments, in order.
    types: tuple[str, ...]


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, at
        shift += 7


def _fields(data: bytes) -> Iterator[tuple[int, int | bytes]]:
    """A message's fields in order: (number, value), a value being a number or bytes."""
    at = 0
    while at < len(data):
        key, at = _varint(data, at)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, at = _varint(data, at)
            yield number, value
        elif wire == 2:
            length, at = _varint(data, at)
            yield number, data[at:at + length]
            at += length
        elif wire in (1, 5):
            width = 8 if wire == 1 else 4
            yield number, data[at:at + width]
            at += width
        else:
            raise ValueError(f"Unexpected wire type {wire}.")


def _message(value: int | bytes) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("Expected a message.")
    return value


def _type(data: bytes) -> str:
    """A cel.expr.Type the way Skjald writes types: int, list<string>, map<string, dyn>."""
    for number, value in _fields(data):
        if number == 2:
            return "null"
        if number in (3, 4) and isinstance(value, int):
            return _PRIMITIVES.get(value, "dyn")
        if number == 5 and isinstance(value, int):
            return _WELL_KNOWN.get(value, "dyn")
        if number == 6:
            inner = [_type(_message(v)) for n, v in _fields(_message(value)) if n == 1]
            return f"list<{inner[0] if inner else 'dyn'}>"
        if number == 7:
            parts = {n: _type(_message(v)) for n, v in _fields(_message(value))}
            return f"map<{parts.get(1, 'dyn')}, {parts.get(2, 'dyn')}>"
        if number == 11:
            return "type"
    return "dyn"


def _entry(data: bytes) -> tuple[int, bytes]:
    """One entry of a map field: its number key and its message."""
    key, found = 0, b""
    for number, value in _fields(data):
        if number == 1 and isinstance(value, int):
            key = value
        elif number == 2:
            found = _message(value)
    return key, found


def _walk(data: bytes) -> Iterator[tuple[int, str, list[int]]]:
    """Every call in an Expr, outermost first: its ID, its function and its operands' IDs."""
    own = 0
    for number, value in _fields(data):
        if number == 2 and isinstance(value, int):
            own = value
    for number, value in _fields(data):
        if number in (2, 3, 4):
            continue
        body = _message(value)
        if number == 6:  # a call: what it's called on, the function, the arguments
            function, operands = "", []
            for part, inner in _fields(body):
                if part == 2:
                    function = _message(inner).decode()
                elif part in (1, 3):
                    operands.append(inner)
            yield own, function, [_id(_message(operand)) for operand in operands]
            for operand in operands:
                yield from _walk(_message(operand))
        elif number == 8:  # a map: each entry's key and value
            for part, inner in _fields(body):
                if part == 2:
                    for piece, expr in _fields(_message(inner)):
                        if piece in (3, 4):
                            yield from _walk(_message(expr))
        else:  # a select's operand, a list's items, the parts of a list function
            for _part, inner in _fields(body):
                if isinstance(inner, bytes) and number in (5, 7, 9) and _is_expr(number, _part):
                    yield from _walk(inner)


def _is_expr(kind: int, part: int) -> bool:
    if kind == 5:  # select: operand
        return part == 1
    if kind == 7:  # list: elements
        return part == 1
    return part in (2, 4, 5, 6, 7)  # comprehension: range, start, condition, step, result


def _id(data: bytes) -> int:
    for number, value in _fields(data):
        if number == 2 and isinstance(value, int):
            return value
    return 0


def calls(serialized: bytes) -> list[Call]:
    """The calls of a checked expression, from Expression.serialize()."""
    checked = b""
    for number, value in _fields(serialized):  # google.protobuf.Any: type_url, value
        if number == 2:
            checked = _message(value)
    overloads: dict[int, tuple[str, ...]] = {}
    types: dict[int, str] = {}
    tree = b""
    for number, value in _fields(checked):
        if number == 2:  # reference_map: the name and overloads of each call and name
            key, reference = _entry(_message(value))
            overloads[key] = tuple(_message(v).decode() for n, v in _fields(reference) if n == 3)
        elif number == 3:
            key, found = _entry(_message(value))
            types[key] = _type(found)
        elif number == 4:
            tree = _message(value)
    return [Call(function, overloads.get(own, ()), tuple(types.get(i, "dyn") for i in operands))
            for own, function, operands in _walk(tree)]
