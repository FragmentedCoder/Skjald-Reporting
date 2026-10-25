"""Background jobs: work the app hands to the worker (see docs/architecture.md).

The app and the worker share the encrypted database, so a job is a row in it and
no queue server is needed. Claiming one runs in a transaction that holds the
write lock from its start (BEGIN IMMEDIATE), so two workers never take the same
job. A job that fails is tried again a little later, up to MAX_ATTEMPTS times; one
left running by a worker that stopped is put back in the queue. Scheduled work
gets one job per slot (such as "backup/2026-10-25"), so it's never queued twice.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import ForeignKey, Index, String, Text, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import clock
from app.db import Base, UTCDateTime

State = Literal["queued", "running", "done", "failed"]
MAX_ATTEMPTS = 3
# A job running longer than this was left by a worker that stopped.
STALE_AFTER = timedelta(hours=2)
KEEP_FINISHED = timedelta(days=90)

# What each kind of job does: given a session and the job, return what it found
# (stored as the job's result); raise to fail it.
Handler = Callable[[Session, "Job"], dict[str, Any]]
# What's due at a moment: (kind, slot, payload) for each job to queue.
Schedule = Callable[[Session, datetime], list[tuple[str, str, dict[str, Any]]]]
HANDLERS: dict[str, Handler] = {}
SCHEDULES: list[Schedule] = []


def handles(kind: str) -> Callable[[Handler], Handler]:
    """Register a function as the handler for a kind of job."""

    def register(handler: Handler) -> Handler:
        HANDLERS[kind] = handler
        return handler

    return register


def scheduled(schedule: Schedule) -> Schedule:
    """Register a schedule the worker asks, once a minute, what's due."""
    SCHEDULES.append(schedule)
    return schedule


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_state_run_after", "state", "run_after"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(String(10))
    # What the job needs, as JSON. Never secrets: a handler reads those when it runs.
    payload: Mapped[str] = mapped_column(Text)
    # What it found or made, as JSON, for the pages that show it.
    result: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    run_after: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # For scheduled work: one job per slot.
    slot: Mapped[str | None] = mapped_column(String(80), unique=True)

    def data(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.payload)
        return loaded

    def outcome(self) -> dict[str, Any] | None:
        return json.loads(self.result) if self.result else None


def enqueue(
    db: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    run_after: datetime | None = None,
    requested_by: int | None = None,
    slot: str | None = None,
) -> Job:
    """Queue a job in the caller's transaction. With a slot already used, the job
    that has it comes back instead of a new one."""
    if slot is not None:
        existing = db.scalar(select(Job).where(Job.slot == slot))
        if existing is not None:
            return existing
    now = clock.utcnow()
    job = Job(kind=kind, state="queued", payload=json.dumps(payload or {}),
              run_after=run_after or now, created_at=now, requested_by=requested_by, slot=slot)
    db.add(job)
    db.flush()
    return job


def claim(db: Session) -> Job | None:
    """Take the next job that's due, and commit that it's running."""
    job = db.scalar(
        select(Job).where(Job.state == "queued", Job.run_after <= clock.utcnow())
        .order_by(Job.run_after, Job.id).limit(1)
    )
    if job is not None:
        job.state = "running"
        job.started_at = clock.utcnow()
        job.attempts += 1
    db.commit()
    return job


def finish(db: Session, job: Job, result: dict[str, Any]) -> None:
    job.state = "done"
    job.result = json.dumps(result)
    job.error = None
    job.finished_at = clock.utcnow()
    db.commit()


def fail(db: Session, job: Job, error: str, *, retry: bool = True) -> None:
    """Record why it failed; queue it again later unless it has had its tries."""
    job.error = error[:2000]
    if retry and job.attempts < MAX_ATTEMPTS:
        job.state = "queued"
        job.run_after = clock.utcnow() + timedelta(minutes=5 * job.attempts)
    else:
        job.state = "failed"
        job.finished_at = clock.utcnow()
    db.commit()


def recover_stale(db: Session) -> int:
    """Put back jobs a stopped worker left running. Returns how many."""
    stale = list(db.scalars(select(Job).where(
        Job.state == "running", Job.started_at < clock.utcnow() - STALE_AFTER)))
    for job in stale:
        job.state = "queued" if job.attempts < MAX_ATTEMPTS else "failed"
        job.error = "The worker stopped while it was running."
        if job.state == "failed":
            job.finished_at = clock.utcnow()
    db.commit()
    return len(stale)


def prune(db: Session) -> int:
    """Forget finished jobs older than KEEP_FINISHED. Returns how many."""
    cutoff = clock.utcnow() - KEEP_FINISHED
    gone = db.execute(delete(Job).where(Job.state.in_(("done", "failed")),
                                        Job.finished_at < cutoff))
    db.commit()
    return int(getattr(gone, "rowcount", 0) or 0)


def queue_due(db: Session, now: datetime) -> int:
    """Queue what the schedules say is due, once per slot. Returns how many are new."""
    new = 0
    for schedule in SCHEDULES:
        for kind, slot, payload in schedule(db, now):
            if db.scalar(select(Job.id).where(Job.slot == slot)) is None:
                enqueue(db, kind, payload, slot=slot)
                new += 1
    db.commit()
    return new


def run_one(db: Session) -> Job | None:
    """Claim the next due job and run it. Returns it, or None when nothing is due."""
    job = claim(db)
    if job is None:
        return None
    handler = HANDLERS.get(job.kind)
    if handler is None:
        fail(db, job, f"Nothing handles jobs of the kind {job.kind!r}.", retry=False)
        return job
    job_id = job.id
    try:
        result = handler(db, job)
    except Exception as exc:  # noqa: BLE001 - any failure fails the job; the worker carries on
        db.rollback()
        again = db.get(Job, job_id)
        assert again is not None
        fail(db, again, f"{type(exc).__name__}: {exc}")
        return again
    finish(db, job, result)
    return job


def latest(db: Session, kind: str, *states: State) -> Job | None:
    """The newest job of a kind, in one of these states if any are given."""
    query = select(Job).where(Job.kind == kind)
    if states:
        query = query.where(Job.state.in_(states))
    return db.scalar(query.order_by(Job.created_at.desc(), Job.id.desc()).limit(1))
