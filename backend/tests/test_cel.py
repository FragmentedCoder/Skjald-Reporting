"""Template expressions on the server, against the files both engines share.

shared/cel/cases.json and the examples in shared/cel/functions.json run here on
cel-expr-python and in the browser's tests on cel-js
(frontend/src/lib/cel/cel.test.ts), so the two engines give the same answers.
"""

from __future__ import annotations

import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.cel import Engine, ExpressionError, Table
from app.cel.engine import LOCALES, parse_type, validate
from app.cel.lexer import LexError, tokenize
from app.cel.library import ALLOWED, BANNED, SIGNATURES

SHARED = Path(__file__).resolve().parents[2] / "shared" / "cel"
CASES = json.loads((SHARED / "cases.json").read_text())
FUNCTIONS = json.loads((SHARED / "functions.json").read_text())
TABLES = {name: Table(t["columns"], t["rows"]) for name, t in CASES["tables"].items()}
EXAMPLES = [(f["name"], ex) for f in FUNCTIONS["functions"] for ex in f["examples"]]


def as_json(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"timestamp": value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if isinstance(value, list):
        return [as_json(v) for v in value]
    if isinstance(value, dict):
        return {k: as_json(v) for k, v in value.items()}
    return value


def same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(actual) == len(expected)
                and all(same(a, e) for a, e in zip(actual, expected, strict=True)))
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(same(actual[k], expected[k]) for k in expected))
    return bool(actual == expected)


def type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, datetime):
        return "timestamp"
    return type(value).__name__.replace("str", "string")


def engine_for(case: dict[str, Any]) -> Engine:
    options = case.get("options", {})
    return Engine(case["declare"], timezone=options.get("timezone", "Europe/Copenhagen"),
                  language=options.get("language", "en"), tables=TABLES)


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["id"])
def test_shared_case(case: dict[str, Any]) -> None:
    engine = engine_for(case)
    if "error" in case:
        with pytest.raises(ExpressionError) as caught:
            engine.evaluate(case["expr"], case["vars"])
        assert caught.value.kind == case["error"]["kind"], caught.value.message
        if "message" in case["error"]:
            assert caught.value.message == case["error"]["message"]
        return
    start = time.perf_counter()
    value = engine.evaluate(case["expr"], case["vars"])
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert same(as_json(value), case["expect"]), as_json(value)
    if "type" in case:
        assert type_of(value) == case["type"]
    if "time_limit_ms" in case:
        assert elapsed_ms < case["time_limit_ms"]
    if "references" in case:
        assert engine.references(case["expr"]) == case["references"]


@pytest.mark.parametrize(("name", "example"), EXAMPLES, ids=[ex["expr"] for _, ex in EXAMPLES])
def test_function_example(name: str, example: dict[str, Any]) -> None:
    assert same(as_json(Engine({}, tables=TABLES).evaluate(example["expr"], {})),
                example["result"])


def test_allowed_functions_follow_the_shared_list() -> None:
    assert {f["name"] for f in FUNCTIONS["functions"]} == ALLOWED
    assert FUNCTIONS["banned"] == BANNED


def test_skjald_functions_follow_the_shared_list() -> None:
    declared = {o["id"]: o["signature"] for f in FUNCTIONS["functions"]
                for o in f["overloads"] if o["where"] == "skjald"}
    assert declared == SIGNATURES


def test_locales_follow_the_shared_list() -> None:
    assert FUNCTIONS["locales"] == LOCALES


def test_every_skjald_function_is_tested() -> None:
    tested = " ".join(c["expr"] for c in CASES["cases"]) + " ".join(e["expr"] for _, e in EXAMPLES)
    names = {f["name"] for f in FUNCTIONS["functions"]
             if any(o["where"] == "skjald" for o in f["overloads"])}
    assert [name for name in sorted(names) if f"{name}(" not in tested] == []


def test_check_gives_the_type() -> None:
    engine = Engine({"answers.cvss": "double", "answers.rows": "list<map<string, dyn>>"})
    assert engine.check("answers.cvss >= 9.0") == "bool"
    assert engine.check("answers.cvss >= 9.0 ? \"Critical\" : \"Lower\"") == "string"
    assert engine.check("[1, 2]") == "list<int>"
    assert engine.check("answers.rows") == "list<map<string, dyn>>"
    assert engine.check("{\"a\": 1.5}") == "map<string, double>"


def test_engine_errors_are_said_plainly() -> None:
    engine = Engine({"answers.title": "string"})
    with pytest.raises(ExpressionError) as caught:
        engine.check("answers.title >= 9.0")
    assert caught.value.message == ">= doesn't work with text and a decimal number."
    with pytest.raises(ExpressionError) as caught:
        engine.evaluate("re_match(\"a\", \"a(?=b)\")", {})
    assert caught.value.message == "invalid perl operator: (?="


def test_missing_values_are_empty() -> None:
    engine = Engine({"answers.n": "int", "answers.when": "timestamp",
                     "answers.tags": "list<string>", "answers.title": "string",
                     "answers.ok": "bool"})
    expr = "answers.n == 0 && answers.title == \"\" && !answers.ok && answers.tags.size() == 0"
    assert engine.evaluate(expr, {}) is True
    assert engine.evaluate("answers.when", {}) == datetime(1970, 1, 1, tzinfo=UTC)


def test_values_must_match_their_types() -> None:
    engine = Engine({"answers.n": "int", "answers.when": "timestamp"})
    for values in ({"answers": {"n": "7"}}, {"answers": {"n": 7.5}}, {"answers": {"n": True}},
                   {"answers": {"when": "2026-10-21T14:30"}}):
        with pytest.raises(ExpressionError) as caught:
            engine.evaluate("answers.n", values)
        assert caught.value.kind == "runtime"
    assert engine.evaluate("answers.n", {"answers": {"n": 7.0}}) == 7


def test_tokens() -> None:
    texts = [t.text for t in tokenize("r'a\\' + b\"x\" + '''q'q''' + \"e\\\"\" 0x1Fu 1.5e-3 .5 7u")]
    assert texts == ["r'a\\'", "+", "b\"x\"", "+", "'''q'q'''", "+", "\"e\\\"\"", "0x1Fu",
                     "1.5e-3", ".5", "7u"]
    for broken in ("\"open", "'''open", "a = b", "a # b", "\"line\nbreak\""):
        with pytest.raises(LexError):
            tokenize(broken)


def test_validate_reads_nested_names_and_locals() -> None:
    declared = {"answers.rows": "list<map<string, dyn>>", "customer.custom.sla": "string"}
    validate("answers.rows.map(r, r.n) + [customer.custom.sla]", declared)
    with pytest.raises(ExpressionError, match="customer.custom on its own"):
        validate("customer.custom", declared)


def test_types_parse() -> None:
    assert str(parse_type("map<string,list<map<string, dyn>>>")) == (
        "map<string, list<map<string, dyn>>>")
    for bad in ("list", "map<string>", "set<int>", "list<int>>", "Int"):
        with pytest.raises(ValueError):
            parse_type(bad)
