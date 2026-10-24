"""Projects: a customer's piece of work, which holds its reports.

Each gets a number of its own, P-<year>-<sequence>, never reused. Archiving a
project makes it, and later its reports, read-only; retention periods count from
the archive date.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from sqlalchemy import Date, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import clock
from app.db import Base, UTCDateTime
from app.policy import Setting

# Traffic Light Protocol 2.0 labels, printed on every page of a report.
Classification = Literal["TLP:CLEAR", "TLP:GREEN", "TLP:AMBER", "TLP:AMBER+STRICT", "TLP:RED"]
DEFAULT_CLASSIFICATION: Classification = "TLP:AMBER"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    responsible_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_contacts.id", ondelete="SET NULL")
    )
    classification: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    archived_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ProjectSite(Base):
    __tablename__ = "project_sites"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("customer_sites.id", ondelete="CASCADE"), primary_key=True, index=True
    )


def next_number(db: Session) -> str:
    """The next project number this year, from a counter that only goes up, so a
    number stays unique even after its project (or customer) is deleted. Every
    transaction holds the write lock from its start, so two can't get the same one."""
    year = clock.utcnow().year
    counter = db.get(Setting, f"project_counter/{year}")
    issued = int(counter.value) + 1 if counter else 1
    db.merge(Setting(key=f"project_counter/{year}", value=str(issued)))
    return f"P-{year}-{issued:04d}"


def site_ids_of(db: Session, project_id: int) -> list[int]:
    return sorted(db.scalars(
        select(ProjectSite.site_id).where(ProjectSite.project_id == project_id)
    ))
