"""Server health for Administrators: checks, space used, software versions.

Each check is its own request, so the page fills in as they finish. The slow
ones (the database's integrity check, re-hashing the audit chain, the call to
Have I Been Pwned) run outside any write transaction, so the rest of Skjald
carries on meanwhile.
"""

from __future__ import annotations

import importlib.metadata
import platform
import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import audit, clock, worker
from app.admin import Admin
from app.audit import AuditEntry
from app.auth import pwned
from app.auth.dependencies import DB
from app.auth.sessions import UserSession
from app.db import check_integrity, engine_of, reading
from app.images import StoredImage
from app.jobs import Job
from app.policy import load_policy
from app.settings import settings
from app.setup import setup_completed_at
from app.users import User

router = APIRouter(prefix="/admin")

STARTED_AT = clock.utcnow()
GIB = 1024**3
# Free space below either limit is a warning; below both halves of it, a problem.
LOW_DISK_FRACTION = 0.15
LOW_DISK_BYTES = 2 * GIB

Status = Literal["ok", "warning", "problem", "off"]


class Check(BaseModel):
    key: str
    label: str
    status: Status
    detail: str


class Usage(BaseModel):
    disk_total_bytes: int
    disk_free_bytes: int
    database_bytes: int
    images_bytes: int
    audit_entries: int
    users: int
    active_users: int
    sessions: int


class Versions(BaseModel):
    skjald: str
    python: str
    sqlite: str
    sqlcipher: str
    schema_version: str | None
    operating_system: str
    kernel: str


class Package(BaseModel):
    name: str
    version: str


class ServerHealth(BaseModel):
    checked_at: datetime
    started_at: datetime
    address: str
    setup_completed_at: str | None
    # The keys of the checks to run, one request each (see run_check).
    checks: list[str]
    usage: Usage
    versions: Versions
    packages: list[Package]


def _operating_system() -> str:
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.partition("=")[2].strip().strip('"')
    except OSError:
        pass
    return platform.system()


def _packages() -> list[Package]:
    found = {
        dist.metadata["Name"].lower(): dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]
    }
    return [Package(name=name, version=version) for name, version in sorted(found.items())]


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _database_check(problems: list[str]) -> Check:
    if not problems:
        return Check(key="database", label="Database", status="ok",
                     detail="Encrypted, and every page passed the integrity check.")
    return Check(key="database", label="Database", status="problem",
                 detail="The integrity check found problems: " + "; ".join(problems[:3]))


def _audit_check(result: audit.ChainCheck) -> Check:
    if result.ok:
        return Check(key="audit_chain", label="Audit log", status="ok",
                     detail=f"Chain intact: {result.entries_checked:,} entries checked.")
    return Check(key="audit_chain", label="Audit log", status="problem",
                 detail=f"The chain breaks at entry {result.first_bad_seq}: {result.problem}.")


def _keys_check() -> Check:
    data_dir = Path(settings.data_dir)
    if not Path(settings.master_key_path).exists() or not (data_dir / "db.key.enc").exists():
        return Check(key="keys", label="Keys", status="problem",
                     detail="The master key or the database key file is missing.")
    if not (data_dir / "backup.key.enc").exists():
        return Check(key="keys", label="Keys", status="warning",
                     detail="There's no backup key yet. It's made with the recovery kit.")
    return Check(key="keys", label="Keys", status="ok",
                 detail="The master, database and backup keys are in place.")


def _disk_check(total: int, free: int) -> Check:
    share = free / total if total else 0
    detail = f"{free / GIB:.1f} GB free of {total / GIB:.1f} GB ({share:.0%})."
    if share < LOW_DISK_FRACTION / 2 and free < LOW_DISK_BYTES / 2:
        status: Status = "problem"
    elif share < LOW_DISK_FRACTION or free < LOW_DISK_BYTES:
        status = "warning"
    else:
        status = "ok"
    return Check(key="disk", label="Disk space", status=status, detail=detail)


def _breach_check(enabled: bool) -> Check:
    label = "Breached-password check"
    if not enabled:
        return Check(key="breach_check", label=label, status="off",
                     detail="Switched off in Security.")
    if pwned.reachable():
        return Check(key="breach_check", label=label, status="ok",
                     detail="Have I Been Pwned answers.")
    return Check(key="breach_check", label=label, status="warning",
                 detail="Skjald can't reach Have I Been Pwned, so new passwords can't be saved "
                 "until it can.")


def _worker_check(beat: datetime | None, failed: int, now: datetime) -> Check:
    label = "Background worker"
    if beat is None:
        return Check(key="worker", label=label, status="problem",
                     detail="The worker hasn't started. Check the worker container.")
    quiet = now - beat
    if quiet > timedelta(minutes=5):
        return Check(key="worker", label=label, status="problem",
                     detail=f"Not heard from for {int(quiet.total_seconds() // 60)} minutes. "
                     "Check the worker container.")
    if failed:
        return Check(key="worker", label=label, status="warning",
                     detail=f"Running, but {failed} job{'s' if failed != 1 else ''} failed in the "
                     "last day.")
    return Check(key="worker", label=label, status="ok", detail="Running.")


def _run_worker(db: Session) -> Check:
    now = clock.utcnow()
    failed = db.scalar(select(func.count()).select_from(Job).where(
        Job.state == "failed", Job.finished_at > now - timedelta(days=1))) or 0
    return _worker_check(worker.last_beat(db), failed, now)


def _run_database(db: Session) -> Check:
    db.commit()  # the check reads every page: hold no write lock meanwhile
    return _database_check(check_integrity(engine_of(db)))


def _run_audit_chain(db: Session) -> Check:
    db.commit()
    with reading(engine_of(db)) as reader:
        return _audit_check(audit.verify(reader))


def _run_keys(db: Session) -> Check:
    return _keys_check()


def _run_disk(db: Session) -> Check:
    disk = shutil.disk_usage(Path(settings.data_dir))
    return _disk_check(disk.total, disk.free)


def _run_breach_check(db: Session) -> Check:
    enabled = load_policy(db).breach_check_enabled
    db.commit()  # a network call follows
    return _breach_check(enabled)


# Each check has its own request, so the page fills in as answers arrive and a
# slow one (the integrity check, the network) holds up nothing else.
CHECKS: dict[str, Callable[[Session], Check]] = {
    "database": _run_database,
    "audit_chain": _run_audit_chain,
    "keys": _run_keys,
    "disk": _run_disk,
    "breach_check": _run_breach_check,
    "worker": _run_worker,
}


@router.get("/health")
def server_health(_: Admin, db: DB) -> ServerHealth:
    """Everything quick: usage, versions, and which checks there are to run."""
    completed = setup_completed_at(db)
    counts = {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "active_users": db.scalar(
            select(func.count()).select_from(User).where(User.is_active)
        ) or 0,
        "sessions": db.scalar(
            select(func.count()).select_from(UserSession).where(UserSession.ended_reason.is_(None))
        ) or 0,
        "audit_entries": db.scalar(select(func.max(AuditEntry.seq))) or 0,
        "images_bytes": db.scalar(select(func.sum(func.length(StoredImage.data)))) or 0,
    }
    schema = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    sqlite_version = str(db.execute(text("SELECT sqlite_version()")).scalar())
    sqlcipher_version = str(db.execute(text("PRAGMA cipher_version")).scalar())
    db.commit()

    data_dir = Path(settings.data_dir)
    disk = shutil.disk_usage(data_dir)
    database_bytes = sum(
        _file_size(data_dir / name) for name in ("skjald.db", "skjald.db-wal", "skjald.db-shm")
    )
    return ServerHealth(
        checked_at=clock.utcnow(),
        started_at=STARTED_AT,
        address=settings.address,
        setup_completed_at=completed,
        checks=list(CHECKS),
        usage=Usage(disk_total_bytes=disk.total, disk_free_bytes=disk.free,
                    database_bytes=database_bytes, **counts),
        versions=Versions(
            skjald=importlib.metadata.version("skjald-backend"),
            python=platform.python_version(),
            sqlite=sqlite_version,
            sqlcipher=sqlcipher_version,
            schema_version=schema,
            operating_system=_operating_system(),
            kernel=platform.release(),
        ),
        packages=_packages(),
    )


@router.get("/health/checks/{key}")
def run_check(key: str, _: Admin, db: DB) -> Check:
    check = CHECKS.get(key)
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such check.")
    return check(db)
