"""What a report's form comes to for a set of answers, worked out on the server.

The browser works the form out as the technician types (frontend/src/lib/templates/
preview.ts: what expressions read, calculated values, what unanswered questions
start as, what's hidden, required or not valid) and lists what keeps the report from
going for review (formChecks.ts, missingAnswers). Whether a report may go for review
can't be the browser's word, so the same is worked out here with Google's engine;
shared/reports/form.json holds the two to the same verdicts.

Answers come from a browser and are trusted for nothing. An answer that isn't the
shape its question keeps (text where a number goes, a list where text goes, text
holding a NUL or half of a character pair, which the engine can't take) is read as
empty: expressions get the empty value, and a required question counts as not
answered. Nothing an answer holds can make this raise. Where the browser reads such
an answer at all, every rule fails there; here the rules still run.

Two things are the server's own. A CVSS answer's score and severity are worked out
from its vector, not taken from the answer. And a whole number must fit the 64 bits
the engine gives one.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.cel import Engine, ExpressionError, Table, dates, numbers
from app.cel.engine import EPOCH, LOCALES, TypeSpec, human, to_cel
from app.templates.answers import check_answer, cvss_score
from app.templates.content import Question, TemplateContent
from app.templates.fields import FIELD_TYPES, PERSON_PARTS
from app.templates.names import declarations, questions
from app.templates.secrets import printed

REQUIRED = "is required."
NOT_VALID = "This answer isn't valid."
CELL_REQUIRED = "This is required."

# Questions answered with one line of text, kept as it's typed.
_TEXTS = frozenset({"text", "ip", "hostname", "mac", "serial", "email", "phone", "barcode",
                    "dropdown", "secret"})
_LISTS = ("repeating", "table")
_MAX_INT = 2**63 - 1
# A moment as answers keep it: the browser's toISOString(), or the same with an offset.
_MOMENT = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]+))?)?"
    r"(Z|[+-][0-9]{2}:[0-9]{2})")
# What JavaScript's trim() takes off: a rule that's nothing else isn't a rule, as in
# the browser, and a signature's name is read without it at either end.
_SPACE = "[\t\n\v\f\r \xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
_NOTHING = re.compile(f"{_SPACE}*")
_ENDS = re.compile(rf"^{_SPACE}+|{_SPACE}+\Z")
# The longest name a signature question takes (signature.ts NAME_MAX), counted as there.
_NAME_MAX = 200
# The first and the last moment Python can write. The engine's binding takes exactly
# these two for the beginning and the end of time and then refuses to run anything, so
# neither is a moment an answer or a calculated value holds.
_NEVER = (datetime.min.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC))
# How far into a long text's document the words are looked for (app/templates/text.py
# keeps a real one within 12 levels and 5,000 nodes).
_DOC_DEPTH = 32
_DOC_NODES = 20_000


class _Failed:
    """What stands in for a value when an expression fails, or gives the wrong kind."""


_FAILED = _Failed()


@dataclass(frozen=True)
class Missing:
    """One thing that keeps a report from going for review."""

    step: str
    question: str
    # The field's own words, or "is required." to follow the question's label.
    message: str


@dataclass(frozen=True)
class FormState:
    # Step and question IDs the form hides, in the form's order.
    hidden: list[str]
    # IDs of the questions required now, in the form's order.
    required: list[str]
    # Question ID and message, for answers that fail their valid_when.
    invalid: dict[str, str]
    # Answers by variable name as expressions read them, calculated ones included:
    # plain values, a moment as ISO text in UTC.
    values: dict[str, Any]
    # What a question not answered yet starts as, by question ID, as answers are kept.
    defaults: dict[str, Any]
    # Expressions that failed: the element's ID and what went wrong.
    errors: list[tuple[str, str]]
    # Everything that keeps the report from going for review, in the form's order.
    missing: list[Missing]


# Answers as they're kept


def _text(value: Any) -> str | None:
    """Text the engine can be given, or None: it cuts text at a NUL and refuses half
    of a character pair, so neither is text an answer holds."""
    if not isinstance(value, str) or "\x00" in value:
        return None
    try:
        value.encode()
    except UnicodeEncodeError:
        return None
    return value


def _number(value: Any) -> int | float | None:
    """A number a form can hold: finite, and no larger than a double."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def _whole(value: int | float) -> int | None:
    """The whole part, if the engine's 64 bits hold it."""
    whole = math.trunc(value)
    return whole if -_MAX_INT - 1 <= whole <= _MAX_INT else None


def _moment(value: Any) -> datetime | None:
    """The moment kept as ISO text with Z or an offset, to the millisecond as the
    browser holds one; None for anything else."""
    match = _MOMENT.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    year, month, day, hour, minute, second, fraction, offset = match.groups()
    try:
        moment = datetime(int(year), int(month), int(day), int(hour), int(minute),
                          int(second or 0), int((fraction or "0").ljust(3, "0")[:3]) * 1000,
                          tzinfo=UTC)
        if offset != "Z":
            sign = 1 if offset[0] == "+" else -1
            moment -= sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6]))
    except (ValueError, OverflowError):
        return None
    return None if moment in _NEVER else moment


def _iso(moment: datetime) -> str:
    """A moment as answers keep it and the browser writes it: 2026-10-21T12:30:00.000Z."""
    at = moment.astimezone(UTC)
    return (f"{at.year:04d}-{at.month:02d}-{at.day:02d}T{at.hour:02d}:{at.minute:02d}:"
            f"{at.second:02d}.{at.microsecond // 1000:03d}Z")


def _doc_text(doc: Any) -> str | None:
    """A long text's words, paragraphs on their own lines, as expressions read them
    (text.ts docText); None if it isn't a document."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        return None
    lines: list[str] = []
    seen = 0
    todo: list[tuple[Any, int]] = [(doc, 0)]
    while todo:
        node, depth = todo.pop()
        seen += 1
        if not isinstance(node, dict) or depth > _DOC_DEPTH or seen > _DOC_NODES:
            return None
        content = node.get("content", [])
        if not isinstance(content, list):
            return None
        if node.get("type") in ("paragraph", "heading"):
            line: list[str] = []
            for child in content:
                seen += 1
                if not isinstance(child, dict) or seen > _DOC_NODES:
                    return None
                if child.get("type") == "text":
                    text = _text(child.get("text", ""))
                    if text is None:
                        return None
                    line.append(text)
                elif child.get("type") == "hardBreak":
                    line.append("\n")
            lines.append("".join(line))
        else:
            # Last in, first out: pushed backwards, the nodes come off in their order.
            todo.extend((child, depth + 1) for child in reversed(content))
    return "\n".join(lines)


def _signed(value: Any) -> tuple[str, datetime] | None:
    """Who signed a signature question and when, or None when the answer isn't signed
    (signature.ts signed): a name typed and confirmed with a tick, kept as {"name",
    "confirmed": true, "at"} with at the moment it was ticked, to the second or finer.
    Anything else isn't signed, an answer from the drawing pad this replaced included."""
    if not isinstance(value, dict) or value.get("confirmed") is not True:
        return None
    name, at = _text(value.get("name")), value.get("at")
    written = _MOMENT.fullmatch(at) if isinstance(at, str) else None
    moment = _moment(at) if written is not None and written.group(6) is not None else None
    if name is None or moment is None:
        return None
    typed = _ENDS.sub("", name)
    if not typed or len(typed.encode("utf-16-le")) // 2 > _NAME_MAX:
        return None
    return typed, moment


def _kept(question: Question, raw: Any) -> Any:
    """The answer, if it's the shape its question keeps; else None, and it's read as empty."""
    kind = question.type
    if raw is None:
        return None
    if kind in _TEXTS:
        return _text(raw)
    if kind == "rich_text":
        return raw if (_text(raw) if isinstance(raw, str) else _doc_text(raw)) is not None else None
    if kind == "number":
        number = _number(raw)
        if number is not None and question.settings["whole"] and _whole(number) is None:
            return None
        return number
    if kind == "datetime":
        return raw if _moment(raw) is not None else None
    if kind == "yes_no":
        return raw if isinstance(raw, bool) else None
    if kind == "multi_select":
        return raw if isinstance(raw, list) and all(_text(v) is not None for v in raw) else None
    if kind == "cvss":
        return raw if isinstance(raw, dict) and _text(raw.get("vector", "")) is not None else None
    if kind in ("photo", "file") or kind in _LISTS:
        return raw if isinstance(raw, list) else None
    if kind == "signature":
        return raw if _signed(raw) is not None else None
    if kind == "person":
        return raw if isinstance(raw, dict) and _text(raw.get("display_name")) else None
    return None


def _empty(question: Question, raw: Any) -> bool:
    """Whether a required question would count as not answered, as "Try it" counts it:
    nothing, no text, nothing chosen, no rows, a CVSS answer with no vector."""
    kept = _kept(question, raw)
    if kept is None or (isinstance(kept, str | list) and not kept):
        return True
    return question.type == "cvss" and not kept.get("vector")


# Answers as expressions read them


def _cell(column: Mapping[str, Any], raw: Any) -> Any:
    """One cell of a row as expressions read it, by its column's type; an empty one as
    that type's empty value."""
    kind = column["type"]
    if kind == "number":
        number = _number(raw)
        if column["settings"]["whole"]:
            return (_whole(number) if number is not None else None) or 0
        return float(number) if number is not None else 0.0
    if kind == "yes_no":
        return raw is True
    if kind == "datetime":
        return _moment(raw) or EPOCH
    return _text(raw) or ""


def _scored(vector: str) -> tuple[float, str]:
    """A CVSS vector's score and severity, worked out here rather than taken from the
    answer; 0 and no severity for no vector or one that isn't well-formed, as the
    form keeps those."""
    try:
        return cvss_score(vector) or (0.0, "")
    except Exception:  # the scoring library's own failures: no score, like a broken vector
        return 0.0, ""


def _read(question: Question, kept: Any) -> Any:
    """One answer as expressions see it (preview.ts answerValue): a secret only as it
    prints, a file only whether there is one."""
    kind, settings = question.type, question.settings
    if kind == "rich_text":
        return "" if kept is None else kept if isinstance(kept, str) else _doc_text(kept)
    if kind == "secret":
        secret = kept or ""
        return {"filled": secret != "", "printed": printed(secret, settings["pdf"])}
    if kind in ("photo", "file"):
        count = len(kept or ())
        return {"filled": count > 0, "count": count}
    if kind == "signature":
        # Not signed, the name is empty and the time is no date, as a date not filled in is.
        name, at = _signed(kept) or ("", None)
        return {"filled": at is not None, "name": name, "time": at}
    if kind == "person":
        picked = kept or {}
        parts = {part: _text(picked.get(part)) or "" for part in PERSON_PARTS}
        return {"filled": parts["display_name"] != "", **parts}
    if kind == "cvss":
        vector = (kept or {}).get("vector", "")
        score, severity = _scored(vector)
        return {"vector": vector, "score": score, "severity": severity}
    if kind == "number":
        return _whole(kept) if kept is not None and settings["whole"] else kept
    if kind == "datetime":
        return _moment(kept)
    if kind in _LISTS:
        return [{column["key"]: _cell(column, row.get(column["key"]) if isinstance(row, dict)
                                      else None)
                 for column in settings["columns"]} for row in kept or ()]
    return kept


def _plain(value: Any) -> Any:
    """What expressions read as plain values: a moment as ISO text in UTC."""
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None  # as JSON writes one in the browser
    if isinstance(value, timedelta):
        return {"@duration": value.total_seconds()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


# What keeps one answer from being sent


def _several(n: int, one: str) -> str:
    return f"{n} {one}{'' if n == 1 else 's'}"


def _check(kind: str, settings: dict[str, Any], value: Any) -> str | None:
    """The answer's own check (app/templates/answers.py). What a number is checked as
    is said there; any other answer is checked as the text it is."""
    if kind == "number":
        return check_answer(kind, settings, value)
    text = _text(value)
    return None if text is None else check_answer(kind, settings, text)


def cell_problem(column: Mapping[str, Any], value: Any) -> str | None:
    """What's wrong with one cell of a row: its type's check, or that its column must
    be filled in."""
    if value is None or value == "":
        return CELL_REQUIRED if column["required"] else None
    return _check(column["type"], column["settings"], value)


def answer_problem(question: Question, value: Any) -> str | None:
    """What's wrong with the answer, or None: the first problem, said so it can stand
    in a list (formChecks.ts answerProblem, in the same words)."""
    kind, s = question.type, question.settings
    if kind == "cvss":
        vector = value.get("vector") if isinstance(value, dict) else None
        return _check("cvss", s, "" if vector is None else vector)
    if kind == "multi_select":
        if not isinstance(value, list):
            return None
        fewest, most = s["min_selected"], s["max_selected"]
        if fewest is not None and len(value) < fewest:
            return f"Choose at least {fewest}."
        if most is not None and len(value) > most:
            return f"Choose at most {most}."
        return None
    if kind in _LISTS:
        rows = value if isinstance(value, list) else []
        fixed = s["rows"] if kind == "table" else None
        if fixed is None:
            if len(rows) < s["min_rows"]:
                return f"Add at least {_several(s['min_rows'], 'row')}."
            if len(rows) > s["max_rows"]:
                return f"Keep it to {_several(s['max_rows'], 'row')}."
        # A table's rows are all there to fill in, written or not; a group's are the
        # ones added.
        for r in range(len(rows) if fixed is None else len(fixed)):
            row = rows[r] if r < len(rows) else None
            for column in s["columns"]:
                problem = cell_problem(
                    column, row.get(column["key"]) if isinstance(row, dict) else None)
                if problem:
                    name = (fixed[r]["label"] if fixed is not None else "") or f"Row {r + 1}"
                    return f"{name}, {column['label']}: {problem}"
        return None
    return _check(kind, s, value)


# Start values and what a value prints as


def _start_value(question: Question, value: Any, zone: ZoneInfo) -> Any:
    """What a question starts as, from what its rule gives, kept as its answers are
    (preview.ts startValue): a date question takes the day (midnight where the report
    is written), a date and time question the minute. None when the rule gives nothing
    the question holds."""
    kind, settings = question.type, question.settings
    if value is None or value == "":
        return None
    start: Any
    if kind == "datetime":
        if not isinstance(value, datetime) or value == EPOCH:
            return None
        try:
            start = _iso(dates.start_of_day(value, zone) if settings["mode"] == "date"
                         else value.replace(second=0, microsecond=0))
        except (OverflowError, ValueError):  # a day at the very end of the calendar
            return None
    elif kind == "number":
        number = _number(value)
        start = number if number is None or not settings["whole"] else math.trunc(number)
    elif kind == "yes_no":
        start = value if isinstance(value, bool) else None
    else:
        start = value if isinstance(value, str) else None
    # Only what the question keeps: text is no start for a list of choices or of rows.
    return _kept(question, start)


def _printed(value: Any, language: str, zone: ZoneInfo) -> str:
    """A value as text in {{ }} prints it, in the report's language (preview.ts printValue)."""
    locale = LOCALES.get(language, LOCALES["en"])
    if value is None:
        return ""
    if isinstance(value, bool):
        return (("Ja" if value else "Nej") if language == "da" else "Yes" if value else "No")
    if isinstance(value, int):
        return numbers.written(value)
    if isinstance(value, float):
        text = numbers.written(value)
        return text if value.is_integer() else text.replace(".", locale["decimal"])
    if isinstance(value, datetime):
        if value == EPOCH:
            return ""
        # A moment at midnight is a date with no time of day: the time is left out.
        try:
            pattern = "d MMMM yyyy" if dates.is_midnight(value, zone) else "d MMMM yyyy, HH:mm"
            return dates.format_date(value, pattern, zone, locale)
        except (OverflowError, ValueError):
            # The last or first hours of the calendar, which in the company's time zone
            # fall outside the years 1 to 9999: nothing Python can write out.
            return ""
    if isinstance(value, list):
        return ", ".join(_printed(item, language, zone) for item in value)
    if isinstance(value, timedelta):
        return dates.format_duration(value.total_seconds(), locale)
    return value if isinstance(value, str) else ""


def _as_declared(value: Any, spec: TypeSpec, name: str) -> Any:
    """A calculated value as the kind it's declared to give, or _FAILED when it's
    another kind (or a whole number or a moment the engine can't be given back)."""
    try:
        kept = to_cel(value, spec, name)
    except (ExpressionError, OverflowError):
        return _FAILED
    if spec.name == "int" and not -_MAX_INT - 1 <= kept <= _MAX_INT:
        return _FAILED
    if isinstance(kept, datetime):
        if kept in _NEVER:
            return _FAILED
        # To the millisecond, as the browser holds one.
        kept = kept.replace(microsecond=kept.microsecond // 1000 * 1000)
    return kept


def _written(expr: str | None) -> bool:
    """Whether a rule is there at all."""
    return expr is not None and not _NOTHING.fullmatch(expr)


def _calculation_order(asked: list[Question], engine: Engine) -> list[Question]:
    """The order calculated values are worked out in: each after the ones it reads."""
    calculated = [q for q in asked if q.type == "calculated" and q.key and _written(q.value)]
    by_key = {q.key: q for q in calculated}

    def reads(question: Question) -> list[Question]:
        try:
            names = engine.references(question.value or "")
        except ExpressionError:
            return []
        found = (by_key.get(name.split(".")[1]) for name in names if name.startswith("answers."))
        return [q for q in found if q is not None]

    ordered: list[Question] = []
    visited: set[str | None] = set()
    for first in calculated:
        if first.key in visited:
            continue
        visited.add(first.key)
        # Each question with the ones it reads still to visit: by hand, not by calling
        # itself, so a long chain can't be too deep for Python.
        path = [(first, iter(reads(first)))]
        while path:
            question, waiting = path[-1]
            following = next((q for q in waiting if q.key not in visited), None)
            if following is None:
                ordered.append(question)
                path.pop()
            else:
                visited.add(following.key)
                path.append((following, iter(reads(following))))
    return ordered


def evaluate(
    content: TemplateContent,
    answers: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    library_names: Mapping[str, str] | None = None,
    library_values: Mapping[str, Any] | None = None,
    tables: Mapping[str, Table] | None = None,
    timezone: str = "Europe/Copenhagen",
) -> FormState:
    """The form for these answers, as preview.ts and "Try it" work it out.

    answers: by question ID, as kept. A question that isn't there isn't answered yet
    and starts as its rule says; one that's None was cleared on purpose and stays
    empty. context: the report's own names (customer, project and so on, as
    app/templates/names.py lists them), nested; library_values: {"vars": ..., "text": ...}.
    """
    zone = ZoneInfo(timezone)
    language = content.settings.language
    engine = Engine(declarations(content, library_names), timezone=timezone, language=language,
                    tables=tables)
    asked = questions(content)
    given: Mapping[str, Any] = answers if isinstance(answers, Mapping) else {}
    read: dict[str, Any] = {}
    for q in asked:
        if q.key and q.type != "calculated":
            read[q.key] = _read(q, _kept(q, given.get(q.id)))
    values = {**context, **(library_values or {}), "answers": read}
    errors: list[tuple[str, str]] = []

    def run(element: str, expr: str) -> Any:
        """What the expression gives; _FAILED, and the failure noted, when it fails."""
        try:
            return engine.evaluate(expr, values)
        except ExpressionError as error:
            errors.append((element, error.message))
            return _FAILED

    order = _calculation_order(asked, engine)

    def calculate(report: bool) -> None:
        # Each kept as the kind of value it's declared to give. One that gives another
        # kind (a whole number that works out as 0.75) is its own question's problem
        # and stays empty, rather than failing every expression that reads the answers.
        for q in order:
            assert q.key is not None
            name = f"answers.{q.key}"
            spec = engine.declarations[name]
            try:
                value = engine.evaluate(q.value or "", values)
            except ExpressionError as error:
                if report:
                    errors.append((q.id, error.message))
                continue
            kept = _as_declared(value, spec, name)
            if kept is not _FAILED:
                read[q.key] = kept
                continue
            read[q.key] = None
            if report:
                gives = _printed(value, language, zone) or "something else"
                errors.append((q.id, f"This should give {human(spec.name)}, but with these "
                                     f"answers it gives {gives}."))

    # What a question starts as may read a calculated value, and a calculated value
    # what a question starts as: the calculated values are worked out, then the start
    # values (in the form's order), then the calculated values again.
    starting = [q for q in asked
                if q.key and q.type != "calculated" and _written(q.default) and q.id not in given]
    if starting:
        calculate(False)
    defaults: dict[str, Any] = {}
    for q in starting:
        assert q.key is not None and q.default is not None
        value = run(q.id, q.default)
        start = None if value is _FAILED else _start_value(q, value, zone)
        if start is not None:
            defaults[q.id] = start
            read[q.key] = _read(q, start)
    calculate(True)

    def shows(element: str, rule: str | None) -> bool:
        # A rule that fails shows what it's on, as in the browser.
        if rule is None or not _written(rule):
            return True
        result = run(element, rule)
        return result is True or result is _FAILED

    hidden: list[str] = []
    required: list[str] = []
    invalid: dict[str, str] = {}
    for step in content.form:
        if not shows(step.id, step.visible_when):
            hidden.append(step.id)
        for q in step.questions:
            if not shows(q.id, q.visible_when):
                hidden.append(q.id)
            needed = (run(q.id, q.required_when) is True
                      if q.required_when is not None and _written(q.required_when) else q.required)
            if needed and FIELD_TYPES[q.type].asks:
                required.append(q.id)
            if (q.valid_when is not None and _written(q.valid_when)
                    and run(q.id, q.valid_when) is False):
                invalid[q.id] = q.valid_message or NOT_VALID

    # Everything that would keep the report from going for review: only questions that
    # are shown, on steps that are shown, and that ask something; one not answered yet
    # counts as what it starts as.
    unseen, needed_now = set(hidden), set(required)
    missing: list[Missing] = []
    for step in content.form:
        if step.id in unseen:
            continue
        for q in step.questions:
            if q.id in unseen or not FIELD_TYPES[q.type].asks or q.type == "calculated":
                continue
            answer = given[q.id] if q.id in given else defaults.get(q.id)
            message = answer_problem(q, answer)
            if message is None:
                message = invalid.get(q.id)
            if message is None and q.id in needed_now and _empty(q, answer):
                message = REQUIRED
            if message is not None:
                missing.append(Missing(step.id, q.id, message))
    return FormState(hidden=hidden, required=required, invalid=invalid, values=_plain(read),
                     defaults=defaults, errors=errors, missing=missing)

