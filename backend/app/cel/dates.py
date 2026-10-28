"""Date helpers for template expressions, in the company's time zone.

The browser has the same helpers (frontend/src/lib/cel/dates.ts); the cases in
shared/cel/cases.json hold both to the same answers, summer time included. A local
time that happens twice (when summer time ends) means the first; one that never
happens (when it starts) is read with the offset from before the change, so it
lands an hour later.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

_DATE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?(Z|[+-]\d{2}:\d{2})?$"
)
# Runs of one letter, quoted text ('' is a quote mark) or anything else.
_PATTERN = re.compile(r"'((?:[^']|'')*)'|([A-Za-z])\2*|[^A-Za-z']+|'")
_TOKENS = frozenset({"yyyy", "yy", "MMMM", "MMM", "MM", "M", "dd", "d", "EEEE",
                     "HH", "H", "mm", "ss"})


def parse_date(text: str, zone: ZoneInfo) -> datetime:
    match = _DATE.match(text)
    if not match:
        raise ValueError(f"{text!r} isn't a date such as 2026-10-21 or 2026-10-21T14:30.")
    year, month, day, hour, minute, second, offset = match.groups()
    naive = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                     int(second or 0))
    if offset is None:
        return naive.replace(tzinfo=zone).astimezone(UTC)
    if offset == "Z":
        return naive.replace(tzinfo=UTC)
    sign = 1 if offset[0] == "+" else -1
    delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6]))
    return (naive - sign * delta).replace(tzinfo=UTC)


def add_days(moment: datetime, days: int, zone: ZoneInfo) -> datetime:
    local = moment.astimezone(zone).replace(tzinfo=None) + timedelta(days=days)
    return local.replace(tzinfo=zone).astimezone(UTC)


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600


def days_between(start: datetime, end: datetime, zone: ZoneInfo) -> int:
    return (end.astimezone(zone).date() - start.astimezone(zone).date()).days


def format_date(moment: datetime, pattern: str, zone: ZoneInfo,
                locale: dict[str, object]) -> str:
    local = moment.astimezone(zone)
    months = locale["months"]
    short_months = locale["short_months"]
    weekdays = locale["weekdays"]
    assert isinstance(months, list) and isinstance(short_months, list)
    assert isinstance(weekdays, list)
    values = {
        "yyyy": f"{local.year:04d}", "yy": f"{local.year % 100:02d}",
        "MMMM": months[local.month - 1], "MMM": short_months[local.month - 1],
        "MM": f"{local.month:02d}", "M": str(local.month),
        "dd": f"{local.day:02d}", "d": str(local.day),
        "EEEE": weekdays[local.weekday()],
        "HH": f"{local.hour:02d}", "H": str(local.hour),
        "mm": f"{local.minute:02d}", "ss": f"{local.second:02d}",
    }
    out: list[str] = []
    for match in _PATTERN.finditer(pattern):
        quoted, letter = match.group(1), match.group(2)
        text = match.group(0)
        if quoted is not None:
            out.append(quoted.replace("''", "'") if quoted else "'")
        elif letter is not None:
            if text not in _TOKENS:
                raise ValueError(f"{text} isn't part of a date pattern: put text in 'quotes'.")
            out.append(str(values[text]))
        elif text == "'":
            raise ValueError("A date pattern has a quote mark that isn't closed.")
        else:
            out.append(text)
    return "".join(out)
