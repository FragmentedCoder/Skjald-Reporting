"""format_number(): numbers written the way the report's language writes them.

Rounding starts from the number as it's written (the shortest text that reads back
as the same double, which Python and JavaScript agree on), so 1.005 rounds to 1.01
the way a person expects, and halves round away from zero. The browser's copy is
frontend/src/lib/cel/numbers.ts. written() is how the browser writes a number it
prints as it is, which there is JavaScript's own String().
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

MAX_DECIMALS = 10


def format_number(value: int | float, decimals: int, decimal_mark: str, group_mark: str) -> str:
    if not 0 <= decimals <= MAX_DECIMALS:
        raise ValueError(f"format_number() takes 0 to {MAX_DECIMALS} decimals.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("format_number() needs a finite number.")
    exact = Decimal(value) if isinstance(value, int) else Decimal(repr(value))
    rounded = exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    whole, _, fraction = f"{abs(rounded):f}".partition(".")
    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    text = group_mark.join(groups) + (decimal_mark + fraction if decimals else "")
    # A number that rounds to zero is written without a minus sign.
    return "-" + text if rounded < 0 else text


def written(value: int | float) -> str:
    """A number as the browser writes one that's printed as it is (JavaScript's
    String()): the fewest digits that read back as the same number, no ".0" on a whole
    one, and an exponent only from 1e21 up and below 0.000001. A whole number too large
    for a double to hold exactly is written as the double nearest to it, as there."""
    number = float(value)
    if math.isnan(number):
        return "NaN"
    if math.isinf(number):
        return "Infinity" if number > 0 else "-Infinity"
    if number == 0:
        return "0"
    sign, digits, exponent = Decimal(repr(number)).normalize().as_tuple()
    assert isinstance(exponent, int)
    text = "".join(str(d) for d in digits)
    point = len(text) + exponent  # where the decimal point goes, counted from the first digit
    if len(text) <= point <= 21:
        out = text + "0" * (point - len(text))
    elif 0 < point <= 21:
        out = text[:point] + "." + text[point:]
    elif -6 < point <= 0:
        out = "0." + "0" * -point + text
    else:
        power = point - 1
        out = (text[0] + ("." + text[1:] if len(text) > 1 else "")
               + "e" + ("+" if power >= 0 else "-") + str(abs(power)))
    return "-" + out if sign else out
