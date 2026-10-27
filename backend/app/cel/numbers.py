"""format_number(): numbers written the way the report's language writes them.

Rounding starts from the number as it's written (the shortest text that reads back
as the same double, which Python and JavaScript agree on), so 1.005 rounds to 1.01
the way a person expects, and halves round away from zero. The browser's copy is
frontend/src/lib/cel/numbers.ts.
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
