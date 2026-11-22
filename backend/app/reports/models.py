"""Reports and who has them checked out, as stored.

A report belongs to a project and is pinned to one published template version,
which never changes. Its title and answers are sealed with the customer's key,
bound to the report, like everything else that says something about a customer;
only its number, state and what access needs stay plain. Deleting a customer
deletes its projects, their reports and the key, so nothing of them can be read
again.

A report is numbered <prefix>-<year>-<n>, such as INC-2026-0142: the template sets
the prefix, and each prefix counts on its own within a year, from a counter that
only goes up, so a number is never used twice.

Before anyone changes a report they check it out: one step of its form, or the
whole report. Others see who holds what and since when.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String, func, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import clock
from app.db import Base, UTCDateTime
from app.policy import Setting
from app.templates.models import TemplateVersion

DRAFT = "draft"
# How long a checkout may sit unused before it's marked stale, unless an
# Administrator sets another time.
DEFAULT_STALE_HOURS = 8
STALE_HOURS_KEY = "report_checkout_stale_hours"
STALE_HOURS_LIMITS = (1, 720)


class Report(Base):
    __tablename__ = "reports"
    # IDs appear in the audit log and in what sealed values are bound to: never reused.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    # The published template version the report is written with. A version a report
    # is pinned to can't be deleted.
    template_version_id: Mapped[int] = mapped_column(
        ForeignKey("template_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=DRAFT)
    # 1, then 2 for the first correction of a signed report, and so on.
    revision: Mapped[int] = mapped_column(Integer, default=1)
    # {"title"} and {"answers"} (by question ID), each sealed with the customer's key:
    # a list of reports opens the titles alone.
    sealed_title: Mapped[bytes] = mapped_column(LargeBinary)
    sealed_answers: Mapped[bytes] = mapped_column(LargeBinary)
    # The site the report is about, one of the project's.
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_sites.id", ondelete="SET NULL"))
    # Counts the saves of its answers, so a browser can tell that someone else saved.
    saves: Mapped[int] = mapped_column(Integer, default=0)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # The last time a save was written to the audit log, and by whom: saves while
    # someone works are logged once every few minutes, not every one.
    logged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    logged_by: Mapped[int | None] = mapped_column(Integer)


class ReportCheckout(Base):
    """One step of a report's form, or the whole report (no step), held by someone."""

    __tablename__ = "report_checkouts"
    __table_args__ = (
        # A step is held once, and so is the whole report.
        Index("ix_report_checkouts_step", "report_id", "step_id", unique=True,
              sqlite_where=text("step_id IS NOT NULL")),
        Index("ix_report_checkouts_whole", "report_id", unique=True,
              sqlite_where=text("step_id IS NULL")),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(String(40))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # The last time its holder saved something under it.
    active_at: Mapped[datetime] = mapped_column(UTCDateTime)


def next_number(db: Session, prefix: str) -> str:
    """The next number for this prefix this year, such as INC-2026-0142. Every
    transaction holds the write lock from its start, so two can't get the same one."""
    year = clock.utcnow().year
    key = f"report_counter/{prefix}-{year}"
    counter = db.get(Setting, key)
    issued = int(counter.value) + 1 if counter else 1
    db.merge(Setting(key=key, value=str(issued)))
    return f"{prefix}-{year}-{issued:04d}"


def stale_hours(db: Session) -> int:
    stored = db.get(Setting, STALE_HOURS_KEY)
    return int(stored.value) if stored else DEFAULT_STALE_HOURS


def set_stale_hours(db: Session, hours: int) -> None:
    db.merge(Setting(key=STALE_HOURS_KEY, value=str(hours)))


def pinned_reports(db: Session, template_id: int) -> int:
    """How many reports are written with any version of a template."""
    count: int | None = db.scalar(
        select(func.count()).select_from(Report)
        .join(TemplateVersion, TemplateVersion.id == Report.template_version_id)
        .where(TemplateVersion.template_id == template_id))
    return count or 0
