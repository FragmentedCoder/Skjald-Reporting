"""A report's answers as they're taken in and as they're given out.

Taken in: each answer is checked for its question's shape before it's kept. A report
saves halfway, so an answer that is merely wrong (an address that isn't one, too
few rows) is kept and said to be a problem (app/reports/form.py). What's refused
is what could never be an answer to that question: another kind of value, a choice
the question doesn't offer, more than a field can ever hold. The server works out
what it can itself rather than take the browser's word: a CVSS vector's score, a
picked person's details, the moment a signature was confirmed.

Given out: a secret never leaves as it is. Readers get whether it's filled in and
how the PDF prints it; seeing it takes a fresh confirmation with multifactor
(app/reports/routes.py).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from app.reports.context import instant
from app.templates.answers import cvss_score
from app.templates.content import Question, TemplateContent
from app.templates.names import questions
from app.templates.secrets import printed
from app.templates.text import RichTextError, check_doc, doc_text

# The most a field ever holds, whatever its question allows: a question's own limit
# (its longest text, its most rows) is a problem to fix, these are refused.
MAX_TEXT = 10_000
MAX_RICH_TEXT = 100_000
MAX_SECRET = 1_000
MAX_ROWS = 500
MAX_NAME = 200
MAX_NUMBER = 1e15
# All of a report's answers, sealed.
MAX_ANSWERS_BYTES = 4 * 1024 * 1024

TEXT_TYPES = frozenset({"text", "serial", "ip", "hostname", "mac", "email", "phone", "barcode"})
UPLOAD_TYPES = frozenset({"file", "photo"})
# What a secret is given out as.
MASKED = "masked"

# Finds the person a person question may pick, by ID: their details now, or None.
PersonFinder = Callable[[str, str], dict[str, str] | None]


class Refused(ValueError):
    """An answer that can't be kept; the message is fit to show."""


def _text(value: Any, label: str, most: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise Refused(f"{label} takes text.")
    if len(value) > most:
        raise Refused(f"{label} takes at most {most:,} characters.")
    return value


def _number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise Refused(f"{label} takes a number.")
    try:
        finite = math.isfinite(value) and abs(value) <= MAX_NUMBER
    except OverflowError:  # a whole number of hundreds of digits
        finite = False
    if not finite:
        raise Refused(f"{label} takes a number no larger than a thousand million million.")
    number: int | float = value
    return number


def _moment(value: Any, label: str) -> str:
    """A moment with its time zone, kept in UTC as the browser writes it."""
    if not isinstance(value, str) or len(value) > 40:
        raise Refused(f"{label} takes a date.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise Refused(f"{label} takes a date.") from None
    if parsed.tzinfo is None:
        raise Refused(f"{label} takes a date with its time zone.")
    try:
        return instant(parsed.astimezone(UTC))
    except (OverflowError, ValueError):
        raise Refused(f"{label} takes a date.") from None


def _choice(value: Any, options: list[dict[str, Any]], label: str) -> str:
    if not isinstance(value, str) or value not in {o["value"] for o in options}:
        raise Refused(f"{label}: choose one of its options.")
    return value


def _cell(column: dict[str, Any], value: Any, label: str) -> Any:
    if value is None or value == "":
        return None
    kind = column["type"]
    if kind == "number":
        return _number(value, label)
    if kind == "yes_no":
        if not isinstance(value, bool):
            raise Refused(f"{label} is yes or no.")
        return value
    if kind == "dropdown":
        return _choice(value, column["settings"].get("options", []), label)
    if kind == "datetime":
        return _moment(value, label)
    return _text(value, label)


def _rows(question: Question, value: Any) -> list[dict[str, Any]]:
    label = question.label
    if not isinstance(value, list):
        raise Refused(f"{label} takes rows.")
    fixed = question.settings.get("rows") if question.type == "table" else None
    most = len(fixed) if fixed is not None else MAX_ROWS
    if len(value) > most:
        raise Refused(f"{label} takes at most {most:,} rows.")
    columns = {c["key"]: c for c in question.settings["columns"]}
    rows: list[dict[str, Any]] = []
    for number, row in enumerate(value, start=1):
        if row is None:
            row = {}
        if not isinstance(row, dict) or not set(row) <= set(columns):
            raise Refused(f"{label}, row {number}: a row holds its columns' cells.")
        rows.append({key: _cell(column, row.get(key), f"{label}, row {number}, {column['label']}")
                     for key, column in columns.items()})
    return rows


def _signature(value: Any, held: Any, label: str, now: datetime) -> dict[str, Any]:
    """A name typed and confirmed by someone who isn't a user of Skjald. The moment
    is the server's, and stays the first one while the name does."""
    if not isinstance(value, dict) or value.get("confirmed") is not True:
        raise Refused(f"{label}: type the name and tick the box to confirm it.")
    name = _text(value.get("name"), label, MAX_NAME).strip()
    if not name:
        raise Refused(f"{label}: type the name and tick the box to confirm it.")
    if (isinstance(held, dict) and held.get("name") == name and held.get("confirmed") is True
            and isinstance(held.get("at"), str)):
        return {"name": name, "confirmed": True, "at": held["at"]}
    return {"name": name, "confirmed": True, "at": instant(now)}


def clean(question: Question, value: Any, held: Any, *, find_person: PersonFinder,
          now: datetime) -> Any:
    """The answer as it's kept, or Refused. Empty answers never get here."""
    label = f"“{question.label}”" if question.label else "This question"
    kind, settings = question.type, question.settings
    if kind in ("calculated", "heading"):
        raise Refused(f"{label} isn't answered: Skjald works it out."
                      if kind == "calculated" else f"{label} is a heading.")
    if kind in UPLOAD_TYPES:
        raise Refused("Files and photos can't be added to a report yet.")
    if kind in TEXT_TYPES:
        return _text(value, label)
    if kind == "rich_text":
        try:
            doc = check_doc(value)
        except RichTextError as error:
            raise Refused(f"{label}: {error}") from None
        if _has_variables(doc):
            raise Refused(f"{label} can't hold names in {{{{ }}}}: they're for templates.")
        if len(doc_text(doc)) > MAX_RICH_TEXT:
            raise Refused(f"{label} takes at most {MAX_RICH_TEXT:,} characters.")
        return doc
    if kind == "number":
        return _number(value, label)
    if kind == "datetime":
        return _moment(value, label)
    if kind == "yes_no":
        if not isinstance(value, bool):
            raise Refused(f"{label} is yes or no.")
        return value
    if kind == "dropdown":
        return _choice(value, settings["options"], label)
    if kind == "multi_select":
        if not isinstance(value, list) or len(value) != len({str(v) for v in value}):
            raise Refused(f"{label}: choose among its options, each once.")
        return [_choice(v, settings["options"], label) for v in value]
    if kind == "cvss":
        vector = _text(value.get("vector") if isinstance(value, dict) else None, label, 300).strip()
        scored = cvss_score(vector)
        return {"vector": vector, "score": scored[0] if scored else 0,
                "severity": scored[1] if scored else ""}
    if kind == "secret":
        if isinstance(value, dict) and value.get(MASKED) is True:
            raise Refused(f"{label} is kept as it is: type a new value to replace it.")
        return _text(value, label, MAX_SECRET)
    if kind == "signature":
        return _signature(value, held, label, now)
    if kind == "person":
        picked = value.get("id") if isinstance(value, dict) else None
        if not isinstance(picked, str):
            raise Refused(f"{label}: choose a person.")
        # The same person stays as they were when picked.
        if isinstance(held, dict) and held.get("id") == picked:
            return held
        found = find_person(str(settings.get("who", "technicians")), picked)
        if found is None:
            raise Refused(f"{label}: that person can't be chosen here.")
        return {"id": picked, **found}
    if kind in ("repeating", "table"):
        return _rows(question, value)
    raise Refused(f"{label} can't be answered here yet.")


def _has_variables(node: Any) -> bool:
    if isinstance(node, dict):
        return node.get("type") == "variable" or any(
            _has_variables(child) for child in node.get("content", []))
    return False


def _blank(question: Question, value: Any) -> bool:
    """Whether what was sent is no answer: nothing, a CVSS answer with no vector, a
    signature whose name isn't typed or isn't confirmed."""
    if value is None or value == "" or value == [] or value == {}:
        return True
    if question.type == "cvss":
        return isinstance(value, dict) and not str(value.get("vector") or "").strip()
    if question.type == "signature":
        return (isinstance(value, dict) and (value.get("confirmed") is not True
                                             or not str(value.get("name") or "").strip()))
    return False


def merge(content: TemplateContent, held: Mapping[str, Any], given: Mapping[str, Any], *,
          find_person: PersonFinder, now: datetime) -> tuple[dict[str, Any], list[str]]:
    """The answers after a save, and the IDs of the questions whose answer changed.

    An answer left empty is forgotten, so the question starts again as its rule
    says, unless it has such a rule: then it's kept as cleared (None), and stays
    empty. Raises Refused for the first answer that can't be kept.
    """
    by_id = {q.id: q for q in questions(content)}
    answers = dict(held)
    changed: list[str] = []
    for question_id, value in given.items():
        question = by_id.get(question_id)
        if question is None:
            raise Refused("That question isn't in this report's template.")
        before = answers.get(question_id, _UNANSWERED)
        if _blank(question, value):
            if question.default and question.default.strip():
                answers[question_id] = None
            else:
                answers.pop(question_id, None)
        else:
            answers[question_id] = clean(question, value, answers.get(question_id),
                                         find_person=find_person, now=now)
        if answers.get(question_id, _UNANSWERED) != before:
            changed.append(question_id)
    return answers, changed


_UNANSWERED = object()


def shown(content: TemplateContent, answers: Mapping[str, Any]) -> dict[str, Any]:
    """The answers as readers get them: a secret only as whether it's filled in and
    how the PDF prints it."""
    secrets = {q.id: q for q in questions(content) if q.type == "secret"}
    out: dict[str, Any] = {}
    for question_id, value in answers.items():
        question = secrets.get(question_id)
        if question is not None and isinstance(value, str) and value:
            out[question_id] = {MASKED: True,
                                "printed": printed(value, question.settings.get("pdf", "partial"))}
        else:
            out[question_id] = value
    return out
