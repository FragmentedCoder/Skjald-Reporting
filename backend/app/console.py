"""Commands for the VM console, for what the web UI can't do.

    docker compose exec app python -m app.console reset-allowlist
    docker compose exec app python -m app.console reset-certificate

reset-allowlist switches off the admin panel and sign-in IP allowlists, for when
they lock every Administrator out. The addresses stay, so they can be switched
on again after fixing them. reset-certificate goes back to Caddy's own
certificate authority, for when the certificate chosen leaves Skjald
unreachable. Running them needs shell access to the VM, which is the point.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from sqlalchemy.orm import Session

from app import audit, tls
from app.policy import load_policy, save_policy


def reset_allowlist(db: Session) -> list[str]:
    """Switch off both allowlists. Returns the ones that were on."""
    policy = load_policy(db)
    were_on = [name for name, on in (("admin panel", policy.admin_allowlist_enabled),
                                     ("sign-in", policy.login_allowlist_enabled)) if on]
    save_policy(db, replace(policy, admin_allowlist_enabled=False, login_allowlist_enabled=False))
    audit.append(db, "admin.allowlist_reset", actor_name="console",
                 details={"switched_off": were_on})
    return were_on


def reset_certificate(db: Session) -> str:
    """Go back to Caddy's own certificate authority. Returns the way it was."""
    before = tls.load_tls(db).mode
    tls.save_tls(db, tls.TlsSettings())
    audit.append(db, "tls.reset", actor_name="console", details={"was": before})
    return before


def main(argv: list[str]) -> int:
    from app.db import get_engine

    if argv not in (["reset-allowlist"], ["reset-certificate"]):
        print(__doc__, file=sys.stderr)
        return 2
    with Session(get_engine()) as db:
        if argv == ["reset-certificate"]:
            before = reset_certificate(db)
            db.commit()
            tls.write_for_caddy(tls.TlsSettings())
            print("Skjald serves the certificate of its own authority again"
                  f"{'' if before == 'internal' else f' (it was {before})'}; Caddy reloads "
                  "within seconds.")
            return 0
        were_on = reset_allowlist(db)
        db.commit()
    if were_on:
        print(f"Switched off the {' and '.join(were_on)} allowlist; Skjald answers from any "
              "address again.")
    else:
        print("Both allowlists were already off.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
