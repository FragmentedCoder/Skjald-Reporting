"""A report's form on the server, against the cases the browser runs too
(frontend/src/lib/templates/reportForm.test.ts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.cel import Table
from app.reports.form import FormState, Missing, evaluate
from app.templates.content import TemplateContent

SHARED = Path(__file__).resolve().parents[2] / "shared"
CASES = json.loads((SHARED / "reports" / "form.json").read_text())["cases"]


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


def test_the_shared_cases_cover_every_kind_of_question_but_a_signature() -> None:
    kinds = {q["type"] for case in CASES for step in case["form"] for q in step["questions"]}
    assert sorted(kinds) == [
        "barcode", "calculated", "cvss", "datetime", "dropdown", "email", "file", "heading",
        "hostname", "ip", "mac", "multi_select", "number", "person", "phone", "photo", "repeating",
        "rich_text", "secret", "serial", "table", "text", "yes_no"]
