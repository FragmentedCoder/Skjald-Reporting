"""Projects: a customer's piece of work, which holds its reports.

Each gets a number of its own, P-<year>-<sequence>, never reused. Its name and
dates are sealed with the customer's key. Archiving a project makes it, and
later its reports, read-only; retention periods count from the archive date.

Everyone who sees a customer fully sees its projects, except a TLP:RED one:
that's for Administrators, Managers and the project's team only (its responsible
technician, its reviewer and the people added to it).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import ForeignKey, LargeBinary, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import clock
from app.db import Base, UTCDateTime
from app.policy import Setting

# Traffic Light Protocol 2.0 labels, printed on every page of a report.
Classification = Literal["TLP:CLEAR", "TLP:GREEN", "TLP:AMBER", "TLP:AMBER+STRICT", "TLP:RED"]
DEFAULT_CLASSIFICATION: Classification = "TLP:AMBER"
# Shared only with the people it was given to: the project's team.
TEAM_ONLY = "TLP:RED"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[str] = mapped_column(String(20), unique=True)
    # {"name", "start_date", "end_date"}, sealed with the customer's key.
    sealed: Mapped[bytes] = mapped_column(LargeBinary)
    responsible_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Reviews and countersigns the project's reports; never its responsible technician.
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
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


class ProjectMember(Base):
    """Someone added to a project's team, besides its responsible technician and reviewer."""

    __tablename__ = "project_members"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


def member_ids(db: Session, project_id: int) -> set[int]:
    return set(db.scalars(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    ))


def team_ids(db: Session, project: Project) -> set[int]:
    """The responsible technician, the reviewer and everyone added to the project."""
    team = member_ids(db, project.id)
    team |= {i for i in (project.responsible_id, project.reviewer_id) if i is not None}
    return team


def projects_joined(db: Session, user_id: int) -> set[int]:
    """Projects someone is on the team of, as member, responsible or reviewer."""
    joined = set(db.scalars(
        select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    ))
    joined |= set(db.scalars(select(Project.id).where(
        (Project.responsible_id == user_id) | (Project.reviewer_id == user_id))))
    return joined


def on_team_only(project: Project) -> bool:
    return project.classification == TEAM_ONLY


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
