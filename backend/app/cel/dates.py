"""Date helpers for template expressions, in the company's time zone.

The browser has the same helpers (frontend/src/lib/cel/dates.ts); the cases in
shared/cel/cases.json hold both to the same answers, summer time included. A local
time that happens twice (when summer time ends) means the first; one that never
happens (when it starts) is read with the offset from before the change, so it
lands an hour later.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.cel import numbers

_DATE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})(?:T([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?)?"
    r"(Z|[+-][0-9]{2}:[0-9]{2})?"
)
# Runs of one letter, quoted text ('' is a quote mark) or anything else.
_PATTERN = re.compile(r"'((?:[^']|'')*)'|([A-Za-z])\2*|[^A-Za-z']+|'")
_TOKENS = frozenset({"yyyy", "yy", "MMMM", "MMM", "MM", "M", "dd", "d", "EEEE",
                     "HH", "H", "mm", "ss"})


def parse_date(text: str, zone: ZoneInfo) -> datetime:
    invalid = ValueError(f"'{text}' isn't a date such as 2026-10-21 or 2026-10-21T14:30.")
    match = _DATE.fullmatch(text)
    if not match:
        raise invalid
    year, month, day, hour, minute, second, offset = match.groups()
    try:
        naive = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                         int(second or 0))
        if offset is None:
            return naive.replace(tzinfo=zone).astimezone(UTC)
        if offset == "Z":
            return naive.replace(tzinfo=UTC)
        sign = 1 if offset[0] == "+" else -1
        delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6]))
        return (naive - sign * delta).replace(tzinfo=UTC)
    except (ValueError, OverflowError):
        # A day the month doesn't have, or a moment outside the years 1 to 9999.
        raise invalid from None


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


def start_of_day(moment: datetime, zone: ZoneInfo) -> datetime:
    """Midnight, where the report is written, of the day a moment falls on."""
    local = moment.astimezone(zone)
    return datetime(local.year, local.month, local.day, tzinfo=zone).astimezone(UTC)


def is_midnight(moment: datetime, zone: ZoneInfo) -> bool:
    """Whether a moment is midnight where the report is written: a date with no time of day."""
    local = moment.astimezone(zone)
    return local.hour == 0 and local.minute == 0 and local.second == 0


def format_duration(seconds: float, locale: Mapping[str, Any]) -> str:
    """A length of time in words, largest unit first, leaving out what's nothing: "3 days
    1 hour", "90 minutes" as "1 hour 30 minutes", "1.5 seconds". Seconds show only when
    there are some; nothing at all is "0 minutes"."""
    total = abs(seconds)
    whole = math.floor(total)
    parts: list[tuple[float, str]] = [
        (whole // 86_400, "day"),
        (whole % 86_400 // 3600, "hour"),
        (whole % 3600 // 60, "minute"),
        # To the millisecond, a half rounding up as the browser's Math.round does.
        (math.floor((whole % 60 + (total - whole)) * 1000 + 0.5) / 1000, "second"),
    ]
    words = [
        f"{numbers.written(n).replace('.', locale['decimal'])} {locale['units'][unit][n != 1]}"
        for n, unit in parts if n != 0]
    if not words:
        return f"0 {locale['units']['minute'][1]}"
    return ("-" if seconds < 0 else "") + " ".join(words)
