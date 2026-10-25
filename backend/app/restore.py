"""Restore a backup: `python -m app.restore`, with Skjald stopped.

    docker compose stop app worker
    docker compose run --rm --no-deps worker python -m app.restore
    docker compose up -d

It asks for the backup key from the recovery kit, restores the snapshot (the
newest unless --snapshot says otherwise) into a scratch folder and checks it as
the weekly restore test does. Only then does it move the current data aside, into
a folder named for the time (nothing is deleted), and put the restored copy in
its place. On a new server, put the recovery kit's master key in
/etc/skjald/master.key first (the installer does it with --restore-master-key).
A backup made before the master key was rotated asks for the master key it was
made under, and the restored copy is moved to the server's current one.

The target comes from Skjald's own settings when the database still opens;
otherwise give --repository (such as /backups/restic, or an s3: or rclone:
address), with the credentials restic and rclone read from the environment
(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, RCLONE_CONFIG_SKJALDSMB_...).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.backups import (
    HOST,
    KEY_FILES,
    BackupError,
    check_restored,
    environment,
    load_target,
    password,
    restic,
)
from app.crypto.keys import from_kit_text, load_master_key
from app.crypto.rotation import key_id, opens, rewrap_restored
from app.db import make_engine
from app.jobs import Job
from app.sealed_settings import load_secrets
from app.settings import settings

DATA_FILES = ("skjald.db", "skjald.db-wal", "skjald.db-shm", *KEY_FILES)


def _settle_jobs(folder: Path) -> None:
    """Jobs the copy shows running were running when the backup was made (the backup
    itself, at least). Nothing runs them after a restore, so they're marked failed:
    left running, they'd look busy forever and keep the same job from being asked
    for again."""
    engine = make_engine(folder, settings.master_key_path)
    try:
        with Session(engine) as db:
            for job in db.scalars(select(Job).where(Job.state == "running")):
                job.state, job.finished_at = "failed", clock.utcnow()
                job.error = "It was running when the backup was made; the restore ended it."
            db.commit()
    finally:
        engine.dispose()


# Asked for the master key a backup was made under (named by its ID, if the backup
# says), when it isn't the server's own.
OlderKey = Callable[[str | None], bytes]


def restore(env: dict[str, str], snapshot: str, data_dir: Path,
            older_key: OlderKey | None = None) -> dict[str, Any]:
    """Restore a snapshot into data_dir, keeping what was there in a folder beside it.
    Returns what the check found, and where the old data went."""
    scratch = data_dir / ".restore"
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        restic(env, "restore", snapshot, "--host", HOST, "--target", str(scratch))
        manifest = next(scratch.rglob("manifest.json"), None)
        if manifest is None:
            raise BackupError("That snapshot has no manifest; it isn't Skjald's.")
        restored = manifest.parent
        made_under = json.loads(manifest.read_text()).get("master_key_id")
        if older_key is not None and not opens(restored, load_master_key(settings.master_key_path)):
            old = older_key(made_under)
            if not opens(restored, old):
                raise BackupError("That master key doesn't open this backup either.")
            rewrap_restored(restored, old, settings.master_key_path)
        found = check_restored(restored)
        _settle_jobs(restored)
        kept = data_dir / f".before-restore-{clock.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
        kept.mkdir(mode=0o700)
        for name in DATA_FILES:
            if (data_dir / name).exists():
                (data_dir / name).rename(kept / name)
        for name in ("skjald.db", *KEY_FILES):
            if (restored / name).exists():
                (restored / name).rename(data_dir / name)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return found | {"kept": str(kept)}


def _target_environment(key_text: str, repository: str | None) -> dict[str, str]:
    """restic's environment: from the saved target, or from --repository and the
    credentials already in this process's environment."""
    if repository:
        return {**os.environ, "RESTIC_REPOSITORY": repository, "RESTIC_PASSWORD": key_text,
                "RESTIC_CACHE_DIR": "/tmp/restic-cache", "HOME": "/tmp"}
    engine = make_engine()
    try:
        with Session(engine) as db:
            return environment(load_target(db), load_secrets(db, "backup"), key_text)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore Skjald from a backup.")
    parser.add_argument("--snapshot", default="latest", help="snapshot ID (default: latest)")
    parser.add_argument("--repository", help="restic repository, if Skjald's settings are gone")
    parser.add_argument("--yes", action="store_true", help="don't ask before replacing data")
    args = parser.parse_args(argv)

    kit = getpass.getpass("Backup key, from the recovery kit: ")
    try:
        key_text = password(from_kit_text(kit))
    except ValueError:
        print("That isn't a backup key as the recovery kit writes it.", file=sys.stderr)
        return 2
    try:
        env = _target_environment(key_text, args.repository)
    except Exception as exc:  # noqa: BLE001 - the database may be the thing that's lost
        print(f"Skjald's settings can't be read ({exc}); give --repository.", file=sys.stderr)
        return 2
    data_dir = Path(settings.data_dir)
    if not args.yes:
        print(f"This replaces the data in {data_dir} with snapshot {args.snapshot!r} from "
              f"{env['RESTIC_REPOSITORY']}. The current data is kept beside it. Skjald must "
              "be stopped.")
        if input("Type restore to go on: ").strip() != "restore":
            print("Nothing changed.")
            return 1
    current = key_id(load_master_key(settings.master_key_path))

    def ask(made_under: str | None) -> bytes:
        print(f"This backup was made under master key {made_under or 'an earlier one'}, "
              f"not this server's ({current}): the master key was rotated since.", flush=True)
        text = getpass.getpass("That master key, from the recovery kit kept then: ")
        try:
            return from_kit_text(text)
        except ValueError as exc:
            raise BackupError("That isn't a master key as the recovery kit writes it.") from exc

    try:
        found = restore(env, args.snapshot, data_dir, older_key=ask)
    except BackupError as exc:
        print(f"Not restored: {exc}", file=sys.stderr)
        return 1
    print(f"Restored: schema {found['schema']}, {found['audit_entries']:,} audit log entries, "
          f"backed up {found['made_at']}. The data that was there is in {found['kept']}.")
    if not os.environ.get("SKJALD_COMMAND"):  # skjald restore starts it again itself
        print("Start Skjald again with: skjald start (or docker compose up -d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
