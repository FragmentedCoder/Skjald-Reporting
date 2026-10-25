"""Commands for the server's console, for what the web UI can't do. The skjald
command on the server runs them (deploy/skjald); each also runs as

    docker compose exec app python -m app.console <command>

    status              how Skjald is: every health check, and the master key's ID
    backup              back up now, and wait for it
    restore-test        restore the newest backup into a scratch folder and check it
    rotate-master-key   replace the master key (with Skjald stopped, in the tools
                        service, which may write to /etc/skjald)
    reset-allowlist     switch off both IP allowlists, when they lock everyone out
    reset-certificate   go back to Caddy's own certificate authority, when the
                        certificate chosen leaves Skjald unreachable

The allowlist addresses stay, so they can be switched on again after fixing them.
Running any of these needs shell access to the server, which is the point.
"""

from __future__ import annotations

import sys
import time
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock, jobs, tls
from app.policy import load_policy, save_policy

STATUS_WORDS = {"ok": "OK", "warning": "Warning", "problem": "Problem", "off": "Off"}
# The worker beats every minute; longer than this and it isn't running.
WORKER_GONE = timedelta(minutes=3)


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


def status(db: Session) -> int:
    """Print every health check; 1 if any has a problem."""
    from sqlalchemy import text

    from app.maintenance import CHECKS
    from app.settings import settings
    from app.setup import setup_completed_at

    schema = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    completed = setup_completed_at(db)
    db.commit()
    print(f"Skjald at {settings.address}, schema {schema}, "
          f"{'set up ' + completed if completed else 'not set up yet'}.\n")
    problems = 0
    for run in CHECKS.values():
        check = run(db)
        problems += check.status == "problem"
        print(f"  {STATUS_WORDS[check.status]:<8} {check.label:<22} {check.detail}")
    return 1 if problems else 0


def _worker_running(db: Session) -> bool:
    from app.worker import last_beat

    beat = last_beat(db)
    return beat is not None and clock.utcnow() - beat < WORKER_GONE


def _said(job: jobs.Job) -> str:
    result = job.outcome() or {}
    if job.kind == "backup":
        return (f"backed up {int(result.get('bytes', 0)):,} bytes "
                f"({int(result.get('added', 0)):,} new), snapshot {result.get('snapshot')}")
    return (f"restored snapshot {result.get('snapshot')}: the database and "
            f"{int(result.get('audit_entries', 0)):,} audit log entries check out")


def run_and_wait(db: Session, kind: str, timeout: float = 3 * 3600, poll: float = 2) -> int:
    """Queue a backup or restore test for the worker (or join one already waiting),
    and wait for it."""
    from app.backups import load_target

    names = {"backup": "Backup", "restore_test": "Restore test"}
    if load_target(db).kind == "off":
        print("Backups are switched off (Admin, Backups).", file=sys.stderr)
        return 1
    if not _worker_running(db):
        print("The worker isn't running, so nothing would do it: start Skjald first.",
              file=sys.stderr)
        return 1
    job = db.scalar(select(jobs.Job).where(jobs.Job.kind == kind,
                                           jobs.Job.state.in_(("queued", "running"))).limit(1))
    if job is None:
        job = jobs.enqueue(db, kind, {"via": "console"})
        audit.append(db, f"backup.{kind}_requested", actor_name="console",
                     details={"job": job.id})
    job_id = job.id
    db.commit()
    print(f"{names[kind]} {job_id}: waiting for the worker…", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = db.get(jobs.Job, job_id, populate_existing=True)
        db.commit()
        if job is None:
            break
        if job.state == "done":
            print(f"{names[kind]}: {_said(job)}.")
            return 0
        if job.state == "failed" or (job.state == "queued" and job.error):
            retry = "; the worker tries again later" if job.state == "queued" else ""
            print(f"{names[kind]} failed: {job.error}{retry}", file=sys.stderr)
            return 1
        time.sleep(poll)
    print(f"{names[kind]} {job_id} hasn't finished; it goes on in the worker.", file=sys.stderr)
    return 1


def rotate_master_key() -> int:
    """Finish or undo a rotation left halfway, or replace the master key."""
    from sqlalchemy.orm import Session as _Session

    from app.backups import load_target
    from app.crypto import rotation
    from app.crypto.keys import to_kit_text
    from app.db import make_engine
    from app.settings import settings

    data_dir, path = settings.data_dir, settings.master_key_path
    try:
        resumed = rotation.resume(data_dir, path)
        if resumed:
            print(f"A rotation that stopped halfway is {resumed} now.")
            if resumed == "finished":
                return 0
        engine = make_engine(data_dir, path)
        try:
            with _Session(engine) as db:
                if _worker_running(db):
                    print("The worker is running: stop Skjald first (skjald keys rotate does).",
                          file=sys.stderr)
                    return 1
                db.commit()
        finally:
            engine.dispose()
        rotated = rotation.rotate(data_dir, path)
    except PermissionError:
        print(f"{path} can't be written here: run it with skjald keys rotate.", file=sys.stderr)
        return 1
    except rotation.RotationError as exc:
        print(f"Not rotated: {exc}", file=sys.stderr)
        return 1
    engine = make_engine(data_dir, path)
    try:
        with _Session(engine) as db:
            keep_days = load_target(db).keep_days
            db.commit()
    finally:
        engine.dispose()
    print(
        f"The master key is replaced: {rotated.old_id} -> {rotated.new_id}. The database, "
        f"backup and config keys and {rotated.customer_keys} customer keys are wrapped "
        "with the new one.\n\n"
        "The new master key, for the recovery kit (put it in place of the old one):\n\n"
        f"    {to_kit_text(rotated.new_key)}\n\n"
        f"Keep the old master key ({rotated.old_id}) with the kit until the backups made "
        f"before now have aged out, after {keep_days} days: restoring one of them asks "
        "for it.")
    return 0


def main(argv: list[str]) -> int:
    from app.db import get_engine

    commands = ("status", "backup", "restore-test", "rotate-master-key", "reset-allowlist",
                "reset-certificate")
    if len(argv) != 1 or argv[0] not in commands:
        print(__doc__, file=sys.stderr)
        return 2
    command = argv[0]
    if command == "rotate-master-key":
        return rotate_master_key()
    # Nothing reloads after a commit: reading a job while waiting must not start a
    # transaction, which would hold the write lock the worker needs.
    with Session(get_engine(), expire_on_commit=False) as db:
        if command == "status":
            return status(db)
        if command in ("backup", "restore-test"):
            import app.backups  # noqa: F401 - registers the job kinds

            return run_and_wait(db, command.replace("-", "_"))
        if command == "reset-certificate":
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
