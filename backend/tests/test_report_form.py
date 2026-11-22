"""A report's form on the server, against the cases the browser runs too
(frontend/src/lib/templates/reportForm.test.ts), and what only the server must stand:
answers of any shape, from a browser that's trusted for nothing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.cel import Table
from app.reports.form import FormState, Missing, answer_problem, cell_problem, evaluate
from app.templates.content import Question, TemplateContent
from app.templates.fields import FIELD_TYPES

SHARED = Path(__file__).resolve().parents[2] / "shared"
CASES = json.loads((SHARED / "reports" / "form.json").read_text())["cases"]
V31 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
OPTIONS = [{"value": "low", "label": "Low"}, {"value": "high", "label": "High"}]


def sample_context() -> dict[str, dict[str, Any]]:
    """The sample context "Try it" starts from: the examples in shared/templates/names.json."""
    context: dict[str, dict[str, Any]] = {}
    for group in json.loads((SHARED / "templates" / "names.json").read_text())["groups"]:
        for name in group["names"]:
            root, part = name["name"].split(".")
            context.setdefault(root, {})[part] = name["example"]
    return context


def content_of(form: list[dict[str, Any]], language: str = "en") -> TemplateContent:
    return TemplateContent.model_validate(
        {"schema": 1, "settings": {"language": language}, "form": form, "layout": []})


def one_step(*questions: dict[str, Any]) -> TemplateContent:
    return content_of([{"id": "s_step", "title": "Step", "questions": list(questions)}])


def ask(id_: str, key: str, type_: str, **more: Any) -> dict[str, Any]:
    return {"id": id_, "key": key, "type": type_, "label": key, **more}


def state_of(case: dict[str, Any]) -> FormState:
    context = sample_context()
    for group, values in case.get("context", {}).items():
        context[group].update(values)
    library = case.get("library")
    return evaluate(
        content_of(case["form"], case.get("language", "en")), case["answers"], context,
        library_names=library["names"] if library else None,
        library_values=library["values"] if library else None,
        tables=({name: Table(t["columns"], t["rows"]) for name, t in library["tables"].items()}
                if library else None),
        timezone=case.get("timezone", "Europe/Copenhagen"))


def same(found: Any, expected: Any) -> bool:
    """Equal as JSON carries them to a browser: 3 and 3.0 are one number, true isn't 1."""
    if isinstance(found, bool) or isinstance(expected, bool):
        return found is expected
    if isinstance(found, int | float) and isinstance(expected, int | float):
        return found == expected
    if isinstance(found, list) and isinstance(expected, list):
        return len(found) == len(expected) and all(
            same(a, b) for a, b in zip(found, expected, strict=True))
    if isinstance(found, dict) and isinstance(expected, dict):
        return found.keys() == expected.keys() and all(same(found[k], expected[k]) for k in found)
    return type(found) is type(expected) and bool(found == expected)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"][:70])
def test_shared_case(case: dict[str, Any]) -> None:
    state, expected = state_of(case), case["expect"]
    assert same(state.values, expected["values"]), state.values
    assert same(state.defaults, expected["defaults"]), state.defaults
    assert state.hidden == expected["hidden"]
    assert state.required == expected["required"]
    assert state.invalid == expected["invalid"]
    assert state.missing == [Missing(**m) for m in expected["missing"]]
    # Which expressions fail, and in Skjald's own sentences where they're its own.
    assert [element for element, _ in state.errors] == [e["element"] for e in expected["errors"]]
    for (_, message), error in zip(state.errors, expected["errors"], strict=True):
        assert message == error.get("message", message)
    # What comes back goes into JSON as it is.
    json.dumps([state.values, state.defaults], allow_nan=False)


def test_the_shared_cases_cover_every_kind_of_question() -> None:
    kinds = {q["type"] for case in CASES for step in case["form"] for q in step["questions"]}
    assert kinds == set(FIELD_TYPES)


# What the server has to itself

EVERY = [
    ask("q_text", "text", "text", required=True),
    ask("q_long", "long", "rich_text", required=True),
    ask("q_amount", "amount", "number", required=True),
    ask("q_count", "count", "number", required=True, settings={"whole": True}),
    ask("q_when", "when", "datetime", required=True),
    ask("q_agreed", "agreed", "yes_no", required=True),
    ask("q_level", "level", "dropdown", required=True, settings={"options": OPTIONS}),
    ask("q_levels", "levels", "multi_select", required=True, settings={"options": OPTIONS}),
    ask("q_address", "address", "ip", required=True),
    ask("q_score", "score", "cvss", required=True),
    ask("q_secret", "secret", "secret", required=True),
    ask("q_files", "files", "file", required=True),
    ask("q_photos", "photos", "photo", required=True),
    ask("q_person", "person", "person", required=True),
    ask("q_signed", "signed", "signature", required=True),
    ask("q_rows", "rows", "repeating", required=True, settings={"columns": [
        {"key": "host", "label": "Host", "type": "text"},
        {"key": "port", "label": "Port", "type": "number", "settings": {"whole": True}},
        {"key": "hours", "label": "Hours", "type": "number"},
        {"key": "open", "label": "Open", "type": "yes_no"},
        {"key": "seen", "label": "Seen", "type": "datetime"}]}),
    ask("q_week", "week", "table", required=True, settings={
        "rows": [{"key": "mon", "label": "Monday"}],
        "columns": [{"key": "hours", "label": "Hours", "type": "number"}]}),
    # Rules that read every answer: none may fail, whatever the answers are.
    ask("q_reads", "reads", "calculated", settings={"result": "yes_no"}, value=(
        'answers.text == "" && answers.long == "" && answers.amount == 0.0 && answers.count == 0'
        ' && !has(answers.when) && !answers.agreed && answers.level == ""'
        " && answers.levels.size() == 0 && !has(answers.address) && answers.score.score == 0.0"
        ' && answers.score.vector == "" && !answers.secret.filled && answers.files.count == 0'
        " && !answers.photos.filled && !answers.person.filled && !answers.signed.filled"
        " && answers.rows.all(r, r.host == \"\" && r.port == 0 && r.hours == 0.0 && !r.open"
        ' && format_date(r.seen, "yyyy") == "") && answers.week.all(r, r.hours == 0.0)')),
]
EMPTY_VALUES = {
    "text": None, "long": "", "amount": None, "count": None, "when": None, "agreed": None,
    "level": None, "levels": None, "address": None,
    "score": {"vector": "", "score": 0.0, "severity": ""},
    "secret": {"filled": False, "printed": ""}, "files": {"filled": False, "count": 0},
    "photos": {"filled": False, "count": 0},
    "person": {"filled": False, **{part: "" for part in (
        "display_name", "first_name", "middle_name", "last_name", "job_title", "department",
        "company", "email", "phone")}},
    "signed": {"filled": False, "name": "", "time": None},
}
SIGNED = {"name": "Mette Lund", "confirmed": True, "at": "2026-10-21T08:00:00.000Z"}
TEXT_WRONG = [5, 2.5, True, [], ["a"], {}, {"a": 1}, "a\x00b", "half \ud83d"]
NUMBER_WRONG = ["7", True, [], {}, float("nan"), float("inf"), 10**400, -(10**400)]
# For each question above, by variable name: what isn't an answer it keeps.
WRONG: dict[str, list[Any]] = {
    "text": TEXT_WRONG, "level": TEXT_WRONG, "address": TEXT_WRONG, "secret": TEXT_WRONG,
    "long": [5, True, [], {}, {"type": "paragraph"}, {"type": "doc", "content": 5}, "a\x00b",
             {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text",
                                                                           "text": 5}]}]},
             {"type": "doc", "content": [{"type": "paragraph", "content": ["text"]}]}],
    "amount": NUMBER_WRONG, "count": [*NUMBER_WRONG, 2**63, -(2**63) - 1, 1e30],
    "when": [5, True, [], {}, "yesterday", "2026-10-21", "2026-10-21T08:00:00",
             "2026-13-45T00:00:00Z", "2026-10-21T25:00:00Z", "0000-01-01T00:00:00Z",
             "2026-10-21T08:00:00Z\n"],
    "agreed": [0, 1, "yes", "true", [], {}],
    "levels": ["low", 5, {}, [1], ["low", None], ["a\x00"], [["low"]]],
    "score": [V31, 5, [], {"vector": 5}, {"vector": None}, {"vector": "a\x00"}, {"vector": [V31]}],
    "files": ["auth.log", 5, {}, True], "photos": ["a.png", 5, {"0": "a.png"}],
    "person": ["Freja Holm", 5, [], {}, {"display_name": ""}, {"display_name": 7},
               {"display_name": "a\x00"}, {"first_name": "Freja"}],
    "signed": ["Mette Lund", 5, [], {}, {"strokes": [[1, 2, 3, 4]]}, {**SIGNED, "confirmed": "yes"},
               {**SIGNED, "confirmed": 1}, {**SIGNED, "name": ""}, {**SIGNED, "name": 7},
               {**SIGNED, "at": "yesterday"}, {**SIGNED, "at": "2026-10-21T08:00Z"},
               {**SIGNED, "at": 1792569600}, {**SIGNED, "name": "x" * 201},
               {**SIGNED, "name": " \u00a0\t"}, {**SIGNED, "name": "Mette\x00"},
               {"name": "Mette Lund", "confirmed": True}],
}


@pytest.mark.parametrize(("key", "wrong"), [(key, w) for key, all_ in WRONG.items() for w in all_],
                         ids=lambda v: repr(v)[:40])
def test_an_answer_of_the_wrong_shape_is_read_as_empty(key: str, wrong: Any) -> None:
    question = next(q for q in EVERY if q["key"] == key)
    state = evaluate(one_step(*EVERY), {question["id"]: wrong}, sample_context())
    # No rule fails: each reads the empty value, as for a question nobody answered.
    assert state.errors == []
    assert state.values[key] == EMPTY_VALUES[key]
    assert state.values["reads"] is True
    json.dumps([state.values, state.defaults], allow_nan=False)
    # And the question, being required, counts as not answered, unless the field has
    # words of its own for what it was given.
    assert [m.message for m in state.missing if m.question == question["id"]] in (
        ["is required."], ["Enter a number."])


def test_rows_of_the_wrong_shape_are_read_cell_by_cell() -> None:
    content = one_step(*EVERY)
    rows = [{"host": 5, "port": "a", "hours": [], "open": "yes", "seen": 7},
            {"host": "a\x00", "port": 2**70, "hours": float("nan"), "open": 1,
             "seen": "2026-10-21"},
            {"host": ["srv"], "port": True, "hours": 10**400, "open": None, "seen": "garbage"},
            5, "row", None, [], {}]
    blank = {"host": "", "port": 0, "hours": 0.0, "open": False,
             "seen": "1970-01-01T00:00:00.000Z"}
    state = evaluate(content, {"q_rows": rows, "q_week": [{"hours": "seven"}, {"hours": 8}]},
                     sample_context())
    assert state.errors == []
    assert state.values["rows"] == [blank] * 8
    assert [(type(c["port"]), type(c["hours"])) for c in state.values["rows"]] == [(int, float)] * 8
    assert state.values["week"] == [{"hours": 0.0}, {"hours": 8.0}]
    # A cell that should hold a number says so; the rest are just empty.
    assert {m.question: m.message for m in state.missing if m.question in ("q_rows", "q_week")} == {
        "q_rows": "Row 1, Port: Enter a number.", "q_week": "Monday, Hours: Enter a number."}
    # Anything but a list is no rows at all.
    for wrong in (5, "rows", {"0": {"host": "srv"}}, True):
        state = evaluate(content, {"q_rows": wrong, "q_week": wrong}, sample_context())
        assert state.errors == [] and state.values["rows"] == [] and state.values["week"] == []
        assert {m.question: m.message for m in state.missing if m.question in ("q_rows", "q_week")
                } == {"q_rows": "is required.", "q_week": "is required."}


def test_answers_that_are_no_mapping_are_no_answers() -> None:
    content = one_step(*EVERY)
    for answers in (None, [], "answers", 5):
        state = evaluate(content, answers, sample_context())  # type: ignore[arg-type]
        assert state.errors == [] and state.values["reads"] is True
        assert [m.message for m in state.missing] == ["is required."] * 17
        assert state.values == evaluate(content, {}, sample_context()).values


def test_text_the_engine_cant_take_is_no_answer() -> None:
    # The engine cuts text at a NUL and refuses half of a character pair: either
    # would make a rule read something else than was typed, or fail every rule.
    content = one_step(
        ask("q_name", "name", "text", required=True, valid_when='answers.name != "admin"'),
        ask("q_other", "other", "text"),
        ask("q_rows", "rows", "repeating", settings={"columns": [
            {"key": "host", "label": "Host", "type": "text", "required": True}]}))
    for text in ("admin\x00x", "admin\ud83d"):
        state = evaluate(content, {"q_name": text, "q_other": "fine",
                                   "q_rows": [{"host": text}]}, sample_context())
        assert state.errors == [] and state.invalid == {}
        assert state.values == {"name": None, "other": "fine", "rows": [{"host": ""}]}
        assert state.missing == [Missing("s_step", "q_name", "is required.")]


def test_a_cvss_score_is_worked_out_here_not_taken_from_the_answer() -> None:
    content = one_step(
        ask("q_score", "score", "cvss"),
        ask("q_plan", "plan", "text", required_when="answers.score.score >= 9.0"))
    forged = {"vector": V31, "score": 0.1, "severity": "Low"}
    state = evaluate(content, {"q_score": forged}, sample_context())
    assert state.values["score"] == {"vector": V31, "score": 9.8, "severity": "Critical"}
    assert state.required == ["q_plan"]
    # One that isn't a vector has no score, whatever the answer says.
    state = evaluate(content, {"q_score": {**forged, "vector": "CVSS:3.1/AV:N"}}, sample_context())
    assert state.values["score"] == {"vector": "CVSS:3.1/AV:N", "score": 0.0, "severity": ""}
    assert [m.question for m in state.missing] == ["q_score"]


def test_a_signature_is_a_name_confirmed_at_a_moment() -> None:
    content = one_step(
        ask("q_witness", "witness", "signature", required=True),
        ask("q_note", "note", "text", required_when="!answers.witness.filled"),
        ask("q_reads", "reads", "calculated", settings={"result": "text"},
            value='answers.witness.name + format_date(answers.witness.time, " (HH:mm)")'))
    signed = {"name": " Mette Lund ", "confirmed": True, "at": "2026-10-21T10:05:00+02:00"}
    state = evaluate(content, {"q_witness": signed}, sample_context())
    assert state.values == {
        "witness": {"filled": True, "name": "Mette Lund", "time": "2026-10-21T08:05:00.000Z"},
        "note": None, "reads": "Mette Lund (10:05)"}
    assert state.required == ["q_witness"] and state.missing == [] and state.errors == []
    # As long a name as the form takes, an emoji counting as the two it's kept as.
    for name, taken in (("x" * 200, True), ("x" * 201, False), ("🙂" * 100, True),
                        ("🙂" * 100 + "x", False)):
        state = evaluate(content, {"q_witness": {**signed, "name": name}}, sample_context())
        assert state.values["witness"]["filled"] is taken, len(name)
    # Anything else isn't signed: a drawing from the pad this replaced, a name not
    # confirmed, a moment that isn't one.
    unsigned = {"filled": False, "name": "", "time": None}
    for answer in (None, {"strokes": [[10, 10, 50, 40]]}, {**signed, "confirmed": False},
                   {**signed, "name": "  "}, {**signed, "at": None}, {"name": "Mette Lund"},
                   "Mette"):
        state = evaluate(content, {"q_witness": answer}, sample_context())
        assert state.values["witness"] == unsigned and state.values["reads"] == "", answer
        assert state.required == ["q_witness", "q_note"] and state.errors == []
        assert [m.question for m in state.missing] == ["q_witness", "q_note"]
    assert evaluate(content, {}, sample_context()).values["witness"] == unsigned


def test_whole_numbers_are_the_engines_64_bits() -> None:
    content = one_step(
        ask("q_count", "count", "number", settings={"whole": True}, required=True),
        ask("q_grown", "grown", "calculated", settings={"result": "whole"},
            value="double(answers.count) * 1.0e30"),
        ask("q_start", "start", "number", settings={"whole": True}, default="1.0e30"),
        ask("q_next", "next", "calculated", settings={"result": "whole"},
            value="answers.count + answers.grown + answers.start + 1"))
    state = evaluate(content, {"q_count": 2**63 - 1}, sample_context())
    assert state.values == {"count": 2**63 - 1, "start": None, "grown": None}
    assert [element for element, _ in state.errors] == ["q_grown", "q_next"]
    assert state.errors[0][1] == ("This should give a whole number, but with these answers it "
                                  "gives 9.223372036854776e+48.")
    # One past it is no whole number a form holds: every rule still runs.
    state = evaluate(content, {"q_count": 2**63}, sample_context())
    assert state.values == {"count": None, "start": None, "grown": 0, "next": 1}
    assert state.errors == []
    assert state.missing == [Missing("s_step", "q_count", "is required.")]


def test_a_date_at_the_end_of_the_calendar_fails_nothing() -> None:
    # In Copenhagen the last hour of the year 9999 is already the year 10000, which
    # no date here can be: it's printed as nothing and starts nothing, and no more.
    content = one_step(
        ask("q_when", "when", "datetime"),
        ask("q_text", "text", "calculated", settings={"result": "text"}, value="answers.when"),
        ask("q_day1", "day", "datetime", settings={"mode": "date"}, default="answers.when"),
        ask("q_shown", "shown", "calculated", settings={"result": "text"},
            value='format_date(answers.when, "yyyy")'),
        ask("q_other", "other", "text", required_when="1 == 1"))
    state = evaluate(content, {"q_when": "9999-12-31T23:59:59Z"}, sample_context())
    assert state.values["when"] == "9999-12-31T23:59:59.000Z" and state.defaults == {}
    assert state.errors[0] == ("q_text", "This should give text, but with these answers it "
                                         "gives something else.")
    assert [element for element, _ in state.errors] == ["q_text", "q_shown"]
    assert state.required == ["q_other"]


def test_the_first_moment_of_all_is_no_answer() -> None:
    # The engine's binding takes the first moment of the year 1 for the beginning of
    # time and then runs nothing at all: as an answer it would switch every rule off.
    content = one_step(
        ask("q_when", "when", "datetime", required=True),
        ask("q_before", "before", "calculated", settings={"result": "date"},
            value="add_hours(answers.when, -1)"),
        ask("q_other", "other", "text", required_when="1 == 1", valid_when="1 == 2"),
        ask("q_rows", "rows", "repeating", settings={"columns": [
            {"key": "seen", "label": "Seen", "type": "datetime"}]}))
    never = "1970-01-01T00:00:00.000Z"
    for first in ("0001-01-01T00:00:00Z", "0001-01-01T00:00:00.000Z", "0001-01-01T05:30:00+05:30"):
        state = evaluate(content, {"q_when": first, "q_rows": [{"seen": first}]}, sample_context())
        assert state.errors == []
        assert state.values == {"when": None, "other": None, "rows": [{"seen": never}],
                                "before": never}
        assert state.required == ["q_when", "q_other"] and list(state.invalid) == ["q_other"]
        assert [m.question for m in state.missing] == ["q_when", "q_other"]
    # An hour later it's a moment like any other; the hour before it, which a rule
    # then works out, is the one that can't be, and is that rule's own failure.
    state = evaluate(content, {"q_when": "0001-01-01T01:00:00Z"}, sample_context())
    assert state.values["when"] == "0001-01-01T01:00:00.000Z" and "before" not in state.values
    assert [element for element, _ in state.errors] == ["q_before"]
    assert state.required == ["q_when", "q_other"] and list(state.invalid) == ["q_other"]
    # Nor is it kept when a template writes it out: the value stays empty, and the
    # other rules run.
    written = one_step(
        ask("q_first", "first", "calculated", settings={"result": "date"},
            value='timestamp("0001-01-01T00:00:00Z")'),
        ask("q_other", "other", "text", required_when="!has(answers.first)"))
    state = evaluate(written, {}, sample_context())
    assert state.values == {"other": None, "first": None} and state.required == ["q_other"]
    assert [element for element, _ in state.errors] == ["q_first"]


def test_a_long_chain_of_calculated_values_is_followed() -> None:
    # Each reads the next, the last one the answer: as long a chain as a template can
    # hold (500 questions), written from its far end.
    chain = [ask(f"q_calc{n}", f"c{n}", "calculated", settings={"result": "whole"},
                 value=f"answers.c{n + 1} + 1" if n < 498 else "answers.base")
             for n in range(499)]
    content = content_of([
        {"id": "s_first", "title": "First", "questions": chain[:300]},
        {"id": "s_second", "title": "Second", "questions": [
            *chain[300:], ask("q_base", "base", "number", settings={"whole": True})]}])
    state = evaluate(content, {"q_base": 2}, sample_context())
    assert state.errors == [] and state.values["c0"] == 500


def test_a_long_text_is_read_however_deep_and_refused_past_any_real_one() -> None:
    content = one_step(ask("q_long", "long", "rich_text", required=True))

    def nested(depth: int) -> dict[str, Any]:
        node: dict[str, Any] = {"type": "paragraph", "content": [{"type": "text", "text": "deep"}]}
        for _ in range(depth):
            node = {"type": "bulletList", "content": [{"type": "listItem", "content": [node]}]}
        return {"type": "doc", "content": [node]}

    assert evaluate(content, {"q_long": nested(5)}, sample_context()).values["long"] == "deep"
    for answer in (nested(40), {"type": "doc", "content": [{"type": "paragraph"}] * 30_000}):
        state = evaluate(content, {"q_long": answer}, sample_context())
        assert state.values["long"] == "" and [m.message for m in state.missing] == ["is required."]


def test_many_rows_are_refused_before_they_are_read() -> None:
    rows = ask("q_rows", "rows", "repeating", settings={"max_rows": 3, "columns": [
        {"key": "host", "label": "Host", "type": "ip", "required": True}]})
    question = Question.model_validate(rows)
    assert answer_problem(question, [{"host": "nope"}] * 200_000) == "Keep it to 3 rows."
    assert answer_problem(question, [{"host": "nope"}]) == (
        "Row 1, Host: Enter an IP address, such as 198.51.100.23 or 2001:db8::5.")
    assert answer_problem(question, [5]) == "Row 1, Host: This is required."
    assert answer_problem(question, "rows") is None


def test_the_answers_own_problem_takes_any_value() -> None:
    column = {"key": "port", "label": "Port", "type": "number", "required": False,
              "settings": {"whole": True, "min": 1, "max": 65535, "decimals": 1, "unit": ""}}
    assert cell_problem(column, 70000) == "Enter a number from 1 to 65535."
    assert cell_problem(column, "") is None and cell_problem(column, [1]) == "Enter a number."
    everything = [w for all_ in WRONG.values() for w in all_]
    for q in EVERY:
        question = Question.model_validate(q)
        for wrong in everything:
            problem = answer_problem(question, wrong)
            assert problem is None or isinstance(problem, str)
