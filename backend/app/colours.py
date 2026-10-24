"""The colour choices people and Administrators pick from.

Only names travel and are stored; frontend/src/lib/colours.ts holds the actual
colours, each checked for contrast in light and dark mode, and a frontend test
checks it offers exactly these names.
"""

from __future__ import annotations

from typing import Literal

PrimaryColour = Literal["fjord", "pine", "teal", "heather", "rose", "slate"]
AccentColour = Literal["rav", "copper", "moss", "sky", "rose", "violet"]

DEFAULT_PRIMARY: PrimaryColour = "fjord"
DEFAULT_ACCENT: AccentColour = "rav"
