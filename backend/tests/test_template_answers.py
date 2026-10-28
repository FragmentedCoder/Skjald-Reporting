"""Answers to typed questions, against the cases the browser runs too
(frontend/src/lib/templates/answers.test.ts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.templates.answers import check_answer, cvss_score

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "shared" / "fields" / "cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['type']}:{c['value']}"[:60])
def test_shared_case(case: dict[str, Any]) -> None:
    assert check_answer(case["type"], case["settings"], case["value"]) == case["message"]
    if "score" in case:
        assert cvss_score(case["value"]) == (case["score"], case["severity"])


def test_empty_answers_are_not_checked() -> None:
    for type_ in ("ip", "hostname", "mac", "email", "phone", "cvss", "text", "number"):
        assert check_answer(type_, {}, "") is None
        assert check_answer(type_, {}, None) is None


def test_broken_vectors_have_no_score() -> None:
    assert cvss_score("CVSS:3.1/AV:N") is None
