"""How a secret field prints in a report: partly, or not at all (docs/architecture.md).

At most a quarter of its characters and at most three at each end are shown, with a
fixed run of dots that hides its length; a secret shorter than eight characters
prints as dots only. Expressions only ever see this, as answers.<key>.printed, never
the secret. shared/templates/secrets.json holds this and the builder's preview
(frontend/src/lib/templates/secrets.ts) to the same results.
"""

from __future__ import annotations

DOTS = "••••••"


def printed(secret: str, how: str = "partial") -> str:
    if how == "omit" or not secret:
        return ""
    shown = min(3, len(secret) // 4 // 2)
    return secret[:shown] + DOTS + (secret[-shown:] if shown else "")
