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
from zoneinfo import ZoneInfo

import pytest

from app.cel import Engine, ExpressionError, Table, dates, numbers
from app.cel.checked import calls
from app.cel.engine import LOCALES, _engine_message, parse_type, validate
from app.cel.lexer import LexError, tokenize
from app.cel.library import ALLOWED, BANNED, ENGINE, SIGNATURES
from app.cel.reader import TOO_DEEP, Unreadable, read, unquote

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


def test_engine_functions_follow_the_shared_list() -> None:
    declared = {o["id"]: o["signature"] for f in FUNCTIONS["functions"]
                for o in f["overloads"] if o["where"] != "skjald"}
    assert declared == ENGINE


def test_the_engine_calls_its_overloads_what_the_shared_list_does() -> None:
    # One call of each overload the engine brings: the checked tree must name it by
    # the ID in the shared list, or the server would refuse what the list allows.
    engine = Engine({"answers.t": "string", "answers.tags": "list<string>", "answers.n": "int",
                     "answers.m": "map<string, string>"})
    written = {
        "string_replace_string_string": "answers.t.replace(\"a\", \"b\")",
        "string_size": "answers.t.size()", "list_size": "answers.tags.size()",
        "map_size": "answers.m.size()", "size_string": "size(answers.t)",
        "size_list": "size(answers.tags)", "size_map": "size(answers.m)",
        "contains_string": "answers.t.contains(\"a\")",
        "starts_with_string": "answers.t.startsWith(\"a\")",
        "ends_with_string": "answers.t.endsWith(\"a\")",
        "string_upper_ascii": "answers.t.upperAscii()",
        "string_lower_ascii": "answers.t.lowerAscii()", "string_trim": "answers.t.trim()",
        "string_split_string": "answers.t.split(\",\")",
        "list_join_string": "answers.tags.join(\",\")",
        "string_index_of_string": "answers.t.indexOf(\"a\")",
        "string_to_timestamp": "timestamp(answers.t)", "int64_to_timestamp": "timestamp(answers.n)",
        "string_to_duration": "duration(answers.t)",
    }
    assert set(written) == {i for i in ENGINE if not i.endswith("_macro")}
    for overload, expr in written.items():
        found = calls(engine._compile(expr)[0].serialize())
        assert [(c.overloads, c.types[0]) for c in found][0][0] == (overload,), expr


def test_the_checked_tree_is_read() -> None:
    engine = Engine({"answers.rows": "list<map<string, dyn>>", "answers.when": "timestamp",
                     "answers.ok": "bool"})
    found = calls(engine._env.compile(
        "answers.ok ? string(answers.rows[0].n) : answers.when.getFullYear() > 2000 ? \"a\" : \"b\""
    ).serialize())
    assert [(c.function, c.types) for c in found] == [
        ("_?_:_", ("bool", "string", "string")),
        ("string", ("dyn",)),
        ("_[_]", ("list<map<string, dyn>>", "int")),
        ("_?_:_", ("bool", "string", "string")),
        ("_>_", ("int", "int")),
        ("getFullYear", ("timestamp",)),
    ]
    assert "int64_to_string" in found[1].overloads and len(found[1].overloads) > 1


# What goes deeper each time it's written around or after what's there already, from
# which value, and how many times Google's parser follows it (None: without end).
DEEPER = [
    ("answers.n", "{} + answers.n", 31),  # 32 values added in a row
    ("answers.n", "{} * answers.n", 31),
    ("answers.ok", "{} == answers.ok", 31),
    ("answers.n", "(answers.ok ? 1 : 0) + {}", 32),  # 33 ticked boxes counted
    ("answers.n", "answers.n - ({})", 31),
    ("answers.n", "({})", 32),
    ("answers.n", "int({})", 31),
    ("answers.n", "[{}]", 31),
    ("answers.n", "{{\"a\": {}}}", 31),
    ("answers.n", "answers.rows.map(r, {})", 31),
    ("answers.n", "[({})]", 15),  # an item and a pair of brackets: two steps
    ("answers.n + answers.n + answers.n", "[{}]", 29),  # steps inside and in a row add up
    ("answers.t", "{}.trim()", 31),
    ("answers.rows", "{}.filter(r, true)", 31),
    ("answers.rows[0]", "{}.a", 30),
    ("answers.d", "{}[0]", 31),
    ("0", "answers.d[{}]", 31),
    ("answers.ok", "answers.ok ? true : {}", 31),  # IF / ELSE IF
    ("answers.ok", "answers.ok ? ({}) : false", 31),
    ("answers.ok", "!({})", 15),  # a NOT and its brackets: two steps
    ("answers.n", "-({})", 15),
    ("answers.ok", "!!{}", None),  # dropped in pairs
    ("answers.ok", "{} && answers.ok", None),
    ("answers.ok", "answers.ok || ({})", 31),
]


def test_the_depth_limit_is_the_engines_own() -> None:
    # Skjald refuses what Google's parser can't follow, in its own words, and nothing
    # that it can. If the engine's limit moves or it counts another way, the readers
    # (app/cel/reader.py and the browser's copy) should move with it.
    engine = Engine({"answers.n": "int", "answers.ok": "bool", "answers.t": "string",
                     "answers.rows": "list<map<string, dyn>>", "answers.d": "dyn"})
    for value, deeper, most in DEEPER:
        expr, taken = value, []
        for times in range(41):
            try:
                engine._env.compile(expr)
                followed = True
            except RuntimeError as exc:
                # Were the engine ever the one to refuse, it would be in the same words.
                assert _engine_message(str(exc)) == TOO_DEEP, (expr, exc)
                followed = False
            try:
                read(tokenize(expr))
                assert followed, (deeper, times)
                taken.append(times)
            except Unreadable as exc:
                assert exc.message == TOO_DEEP and not followed, (deeper, times)
            expr = deeper.format(expr)
        assert taken == list(range(41 if most is None else most + 1)), deeper


def test_the_reader_gives_calls_maps_and_names_after_a_dot() -> None:
    tokens = tokenize(
        "has(item.ip) && sum([1, 2]) > answers.rows.map(r, {\"a\": r.n, 2: 0}).size()")
    shape = read(tokens)
    assert [(c.name, c.member, len(c.args)) for c in shape.calls] == [
        ("has", False, 1), ("sum", False, 1), ("map", True, 2), ("size", True, 0)]
    assert [[tokens[start].text for start, _ in keys] for keys in shape.maps] == [["\"a\"", "2"]]
    assert shape.calls[0].args[0] in shape.selects
    assert unquote("\"a\\x41\\u00e6\\n\"") == "aAæ\n" and unquote("r'\\d'") == "\\d"
    assert unquote("\"\\q\"") is None and unquote("r'a\\'") is None
    for broken, message in (("1 +", "The expression stops before it's finished."),
                            ("(1 2)", "Unexpected '2' at position 4."),
                            ("a ? b ? 1 : 2 : 3", "An IF inside the first result of another IF "
                                                  "needs brackets around it (position 7).")):
        with pytest.raises(Unreadable) as caught:
            read(tokenize(broken))
        assert caught.value.message == message


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


def test_lists_and_maps_come_back_plain() -> None:
    engine = Engine({"answers.tags": "list<string>", "answers.rows": "list<map<string, dyn>>",
                     "answers.when": "timestamp"})
    values = {"answers": {"tags": ["a", "b"], "when": "2026-10-21T01:14:00Z",
                          "rows": [{"name": "srv-01", "ports": [22, 443], "up": True}]}}
    when = datetime(2026, 10, 21, 1, 14, tzinfo=UTC)
    for expr, expected in (
        ("answers.tags.filter(t, t != \"a\")", ["b"]),
        ("\"a,b\".split(\",\")", ["a", "b"]),
        ("[1, 2.5, \"x\", true, null]", [1, 2.5, "x", True, None]),
        ("answers.rows", values["answers"]["rows"]),
        ("answers.rows[0]", values["answers"]["rows"][0]),
        ("answers.rows.map(r, r.ports)", [[22, 443]]),
        ("{\"when\": [answers.when], \"n\": {1: \"one\"}}", {"when": [when], "n": {1: "one"}}),
    ):
        found = engine.evaluate(expr, values)
        assert found == expected, expr
        # Nothing of the engine's own is left inside: it all goes through JSON.
        assert json.loads(json.dumps(found, default=str)) == json.loads(
            json.dumps(expected, default=str))
    rows = engine.evaluate("answers.rows", values)
    assert type(rows) is list and type(rows[0]) is dict and type(rows[0]["ports"]) is list
    assert [type(port) for port in rows[0]["ports"]] == [int, int]


def test_a_date_in_a_row_is_a_date() -> None:
    # The engine's Python binding refuses a datetime where no type is declared, as in
    # a row's cell; the engine is given it as text and reads the rows through a map()
    # that makes it a date again (app/cel/engine.py, _dated).
    engine = Engine({"answers.rows": "list<map<string, dyn>>", "answers.start": "timestamp",
                     "answers.others": "list<map<string, dyn>>"})
    when = datetime(2026, 10, 21, 12, 30, tzinfo=UTC)
    never = datetime(1970, 1, 1, tzinfo=UTC)
    rows = [{"n": 1, "hours": 3.0, "ok": True, "when": when, "in": "a"},
            {"n": 2, "hours": 2.5, "ok": False, "when": never, "in": ""}]
    values = {"answers": {"start": "2026-10-21T00:00:00Z", "rows": rows, "others": [{"x": 1}]}}
    for expr, expected in (
        ("answers.rows[0].when > answers.start", True),
        ("answers.rows.filter(r, r.when > answers.start).size()", 1),
        ("answers.rows.map(r, r.when)", [when, never]),
        ("answers.rows", rows),
        ("format_date(answers.rows[0].when, \"d MMMM yyyy, HH:mm\")", "21 October 2026, 14:30"),
        ("format_date(answers.rows[1].when, \"d MMMM yyyy\")", ""),
        ("has(answers.rows) && answers.rows.all(r, has(r.when) && !has(r.other))", True),
        ("answers.others.map(o, answers.rows.filter(r, r.n > o.x).map(r, r.when))", [[never]]),
        ("hours_between(answers.start, answers.rows[0].when)", 12.5),
        ("answers.rows[0].when + duration(\"90m\")", datetime(2026, 10, 21, 14, tzinfo=UTC)),
        ("sum(answers.rows.map(r, r.hours * 1.5)) + double(answers.rows[1].n)", 10.25),
        ("answers.rows.map(skjald_row, skjald_row[\"in\"])", ["a", ""]),
    ):
        assert engine.evaluate(expr, values) == expected, expr
    # The caller's own rows are left as they were given.
    assert rows[0]["when"] is when
    # A cell stays of no declared kind wherever its column stands, as the rows are
    # declared: text can be read from the cell beside a date, and a date compared with
    # text is a problem found when the rule runs, not when it's checked.
    first = {"answers": {"rows": [{"when": when, "name": "srv-01"}],
                         "others": [{"from": when, "to": never}]}}
    assert engine.evaluate("answers.rows.exists(r, r.name.startsWith(\"srv\"))", first) is True
    assert engine.evaluate("answers.others.all(r, r.to < r.from)", first) is True
    for expr in ("answers.rows[0].when.startsWith(\"a\")", "answers.others[0].to.size() > 1"):
        with pytest.raises(ExpressionError) as caught:
            engine.evaluate(expr, first)
        assert caught.value.kind == "runtime", expr
    # What a rule is checked as doesn't change, and a problem is said as it was.
    assert engine.check("answers.rows.map(r, r.when)") == "list<dyn>"
    with pytest.raises(ExpressionError) as caught:
        engine.evaluate("answers.rows[0].when > 1", values)
    assert caught.value.message == "> doesn't work with a date and time and a whole number."
    # Reading the rows this way is two or three steps deeper: at the very limit an
    # expression is too deep with a date column, and says so in the same words.
    deepest = "answers.rows.size()"
    for _ in range(30):
        deepest = f"[{deepest}]"
    plain = {"answers": {"rows": [{"n": 1}, {"n": 2}]}}
    assert engine.evaluate(deepest[2:-2], values) == engine.evaluate(deepest[2:-2], plain)
    engine.evaluate(deepest, plain)
    with pytest.raises(ExpressionError) as caught:
        engine.evaluate(deepest, values)
    assert caught.value.message == TOO_DEEP
    # Rows that aren't alike can't be read this way, and the engine refuses the date.
    with pytest.raises(ExpressionError):
        engine.evaluate("answers.rows.size()", {"answers": {"rows": [{"a": when}, {"a": "x"}]}})


def test_the_day_a_moment_falls_on() -> None:
    copenhagen, havana = ZoneInfo("Europe/Copenhagen"), ZoneInfo("America/Havana")
    late = datetime(2026, 10, 21, 22, 30, tzinfo=UTC)  # half past midnight on the 22nd
    assert dates.start_of_day(late, copenhagen) == datetime(2026, 10, 21, 22, tzinfo=UTC)
    assert dates.is_midnight(datetime(2026, 10, 21, 22, tzinfo=UTC), copenhagen)
    assert not dates.is_midnight(late, copenhagen)
    assert not dates.is_midnight(datetime(2026, 10, 21, tzinfo=UTC), copenhagen)
    # The day summer time ends is an hour longer, and still starts at its midnight.
    assert dates.start_of_day(datetime(2026, 10, 25, 20, tzinfo=UTC), copenhagen) == datetime(
        2026, 10, 24, 22, tzinfo=UTC)
    # In Havana summer time starts at midnight, so that day has none: it starts an
    # hour later, as a time that never happens is read everywhere here.
    assert dates.start_of_day(datetime(2026, 3, 8, 12, tzinfo=UTC), havana) == datetime(
        2026, 3, 8, 5, tzinfo=UTC)


def test_lengths_of_time_in_words() -> None:
    en, da = LOCALES["en"], LOCALES["da"]
    for seconds, words in ((5400, "1 hour 30 minutes"), (86_400 * 3 + 3600, "3 days 1 hour"),
                           (1.5, "1.5 seconds"), (61, "1 minute 1 second"), (0, "0 minutes"),
                           (-90, "-1 minute 30 seconds"), (0.0004, "0 minutes"),
                           (59.9995, "60 seconds")):
        assert dates.format_duration(seconds, en) == words, seconds
    assert dates.format_duration(90061.5, da) == "1 dag 1 time 1 minut 1,5 sekunder"


def test_numbers_are_written_as_the_browser_writes_them() -> None:
    for value, text in ((0.1 + 0.2, "0.30000000000000004"), (100.0, "100"), (-1.5, "-1.5"),
                        (1e21, "1e+21"), (123456789012345680000.0, "123456789012345680000"),
                        (1e-7, "1e-7"), (1.5e-7, "1.5e-7"), (0.000001, "0.000001"),
                        (5e-324, "5e-324"), (-0.0, "0"), (7, "7"),
                        (2**60, "1152921504606847000"), (1.7976931348623157e308,
                                                         "1.7976931348623157e+308")):
        assert numbers.written(value) == text, value


def test_engine_errors_are_said_plainly() -> None:
    engine = Engine({"answers.title": "string"})
    with pytest.raises(ExpressionError) as caught:
        engine.check("answers.title >= 9.0")
    assert caught.value.message == ">= doesn't work with text and a decimal number."
    with pytest.raises(ExpressionError) as caught:
        engine.evaluate("re_match(\"a\", \"a(?=b)\")", {})
    assert caught.value.message == (
        "The pattern in re_match() isn't a regular expression Skjald can use (RE2 syntax).")
    with pytest.raises(ExpressionError) as caught:
        engine.evaluate("re_match(\"a\", answers.title)", {"answers": {"title": "a(?=b)"}})
    assert (caught.value.kind, caught.value.message) == (
        "runtime", "The pattern isn't a regular expression Skjald can use (RE2 syntax).")


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


def test_validate_takes_a_half_written_expression() -> None:
    # A draft is saved and a template file imported with rules still being written:
    # validate() refuses what must never be there (matches(), unknown functions and
    # names), and leaves whether the rule reads to the check.
    declared = {"answers.cvss": "double"}
    for unfinished in ("answers.cvss >=", "date()", "answers.cvss ? 1 ? 2 : 3 : 4",
                       "(answers.cvss"):
        assert validate(unfinished, declared)
        with pytest.raises(ExpressionError):
            Engine(declared).check(unfinished)
    for refused in ("answers.cvss.matches(\"9\")", "now()", "answers.nope >="):
        with pytest.raises(ExpressionError) as caught:
            validate(refused, declared)
        assert caught.value.kind == "invalid"


def test_types_parse() -> None:
    assert str(parse_type("map<string,list<map<string, dyn>>>")) == (
        "map<string, list<map<string, dyn>>>")
    for bad in ("list", "map<string>", "set<int>", "list<int>>", "Int"):
        with pytest.raises(ValueError):
            parse_type(bad)
