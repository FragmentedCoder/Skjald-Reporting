"""Backups in the admin panel: where they go, when, for how long, and how they fare.

Administrators only. Changing where backups go always asks the person to confirm
it's them, since it sends every copy of the data somewhere else. Secrets are
written, never read back: the page only learns whether one is set. Running a
backup, a restore test or a connection check queues a job for the worker; the
page follows it by asking for the job.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock, jobs
from app.admin import Admin
from app.auth.dependencies import DB, client_ip, require_step_up
from app.auth.sessions import UserSession
from app.backups import SECRETS, Target, load_target, next_backup, repository, save_target
from app.jobs import Job
from app.sealed_settings import load_secrets, save_secrets
from app.users import User

router = APIRouter(prefix="/admin/backups")

KINDS = ("backup", "restore_test", "backup_check")


class TargetIn(Target):
    # Left out (None) keeps what's kept; an empty string clears it.
    smb_password: str | None = Field(default=None, max_length=200)
    s3_secret_access_key: str | None = Field(default=None, max_length=200)


class Run(BaseModel):
    id: int
    kind: str
    state: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    requested_by: str | None


class BackupStatus(BaseModel):
    target: Target
    smb_password_set: bool
    s3_secret_set: bool
    repository: str
    next_backup_at: datetime | None
    last_backup: Run | None
    last_restore_test: Run | None
    runs: list[Run]


def _run(db: Session, job: Job) -> Run:
    who = db.get(User, job.requested_by) if job.requested_by else None
    return Run(id=job.id, kind=job.kind, state=job.state, created_at=job.created_at,
               started_at=job.started_at, finished_at=job.finished_at, result=job.outcome(),
               error=job.error, requested_by=who.display_name if who else None)


def _log(db: Session, request: Request, admin: UserSession, action: str,
         details: dict[str, Any] | None = None) -> None:
    audit.append(db, action, actor_id=admin.user.id, actor_name=admin.user.username,
                 ip=client_ip(request), details=details)


def _status(db: Session) -> BackupStatus:
    target = load_target(db)
    secrets = load_secrets(db, SECRETS)
    last_backup = jobs.latest(db, "backup", "done")
    now = clock.utcnow()
    done_today = bool(last_backup and last_backup.finished_at
                      and last_backup.finished_at.date() == now.date())
    runs = db.scalars(select(Job).where(Job.kind.in_(KINDS))
                      .order_by(Job.created_at.desc(), Job.id.desc()).limit(20))
    restore_test = jobs.latest(db, "restore_test", "done", "failed")
    return BackupStatus(
        target=target,
        smb_password_set=bool(secrets.get("smb_password")),
        s3_secret_set=bool(secrets.get("s3_secret_access_key")),
        repository=repository(target) if target.kind != "off" else "",
        next_backup_at=next_backup(target, done_today, now),
        last_backup=_run(db, last_backup) if last_backup else None,
        last_restore_test=_run(db, restore_test) if restore_test else None,
        runs=[_run(db, job) for job in runs],
    )


@router.get("")
def backup_status(_: Admin, db: DB) -> BackupStatus:
    return _status(db)


@router.put("")
def change_target(body: TargetIn, request: Request, admin: Admin, db: DB) -> BackupStatus:
    return apply_target(db, request, admin, body, confirm=True)


def apply_target(db: Session, request: Request, admin: UserSession, body: TargetIn,
                 confirm: bool) -> BackupStatus:
    """Save where backups go; with confirm, changing it asks for step-up (the setup
    wizard saves without: the one setting up has just signed in)."""
    target = Target.model_validate(body.model_dump(exclude={"smb_password",
                                                            "s3_secret_access_key"}))
    secrets = load_secrets(db, SECRETS)
    if body.smb_password is not None:
        secrets["smb_password"] = body.smb_password
    if body.s3_secret_access_key is not None:
        secrets["s3_secret_access_key"] = body.s3_secret_access_key
    missing = target.missing()
    if target.kind == "smb" and not secrets.get("smb_password"):
        missing = missing or "An SMB share needs its password."
    if target.kind == "s3" and not secrets.get("s3_secret_access_key"):
        missing = missing or "S3-compatible storage needs its secret key."
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, missing)
    before = load_target(db)
    if confirm and (repository(target) != repository(before) or target.kind != before.kind or (
            body.smb_password is not None or body.s3_secret_access_key is not None)):
        require_step_up(admin, "Confirm it's you to change where backups go.")
    save_target(db, target)
    save_secrets(db, SECRETS, secrets)
    _log(db, request, admin, "backup.settings_changed", {
        "kind": target.kind, "hour": target.hour, "keep_days": target.keep_days})
    db.commit()
    return _status(db)


def _queue(db: Session, request: Request, admin: UserSession, kind: str) -> Run:
    if load_target(db).kind == "off":
        raise HTTPException(status.HTTP_409_CONFLICT, "Backups are switched off.")
    waiting = db.scalar(select(Job).where(Job.kind == kind,
                                          Job.state.in_(("queued", "running"))).limit(1))
    if waiting is not None:
        return _run(db, waiting)
    job = jobs.enqueue(db, kind, requested_by=admin.user.id)
    _log(db, request, admin, f"backup.{kind}_requested", {"job": job.id})
    db.commit()
    return _run(db, job)


Action = Literal["backup", "restore_test", "backup_check"]


@router.post("/run/{kind}")
def run_now(kind: Action, request: Request, admin: Admin, db: DB) -> Run:
    """Back up now, test a restore now, or check the target can be reached."""
    return _queue(db, request, admin, kind)


@router.get("/runs/{run_id}")
def get_run(run_id: int, _: Admin, db: DB) -> Run:
    job = db.get(Job, run_id)
    if job is None or job.kind not in KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such run.")
    return _run(db, job)
