"""The projects API.

Anyone who sees a customer fully sees its projects, except TLP:RED ones: those
are for Administrators, Managers and the project's team (its responsible
technician, its reviewer and the people added to it). Administrators and
Managers create, change, archive and reopen projects and choose who works on
them; technicians and reviewers work in the projects they're on. An archived
project is read-only. A project's name and dates are sealed with the customer's
key, and the audit log names projects by number.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.dependencies import DB, FullSession, client_ip, require
from app.auth.sessions import UserSession
from app.customer_routes import contacts_of, sites_of, visible_customer
from app.customers import (
    Customer,
    CustomerContact,
    CustomerSite,
    Keyring,
    assigned_customer_ids,
    is_assigned,
    may_manage_projects,
    sights,
)
from app.projects import (
    DEFAULT_CLASSIFICATION,
    Classification,
    Project,
    ProjectMember,
    ProjectSite,
    member_ids,
    next_number,
    on_team_only,
    site_ids_of,
    team_ids,
)
from app.roles import Capability, Role, roles_of
from app.users import User

router = APIRouter()

ProjectManager = Annotated[UserSession, Depends(require(Capability.MANAGE_PROJECTS))]

NOT_FOUND = "That project doesn't exist."


class ProjectFields(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    responsible_id: int | None = None
    reviewer_id: int | None = None
    contact_id: int | None = None
    site_ids: list[int] = Field(default=[], max_length=200)
    classification: Classification = DEFAULT_CLASSIFICATION

    @model_validator(mode="after")
    def _dates_in_order(self) -> ProjectFields:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date comes before the start date.")
        return self


class ProjectIn(ProjectFields):
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(ProjectFields):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class TeamUpdate(BaseModel):
    user_ids: list[int] = Field(max_length=200)


class Named(BaseModel):
    id: int
    name: str


class Member(Named):
    roles: list[Role]
    responsible: bool
    reviewer: bool


class ProjectSummary(BaseModel):
    id: int
    number: str
    name: str
    customer: Named
    responsible: Named | None
    reviewer: Named | None
    start_date: date | None
    end_date: date | None
    classification: str
    archived_at: datetime | None


class ProjectDetail(ProjectSummary):
    contact: Named | None
    sites: list[Named]
    team: list[Member]
    created_at: datetime
    may_edit: bool
    may_reopen: bool


def _log(
    db: Session, request: Request, record: UserSession, action: str, project: Project,
    details: dict[str, object] | None = None,
) -> None:
    audit.append(
        db, action, actor_id=record.user.id, actor_name=record.user.username,
        target_type="project", target_id=str(project.id), ip=client_ip(request),
        details={"number": project.number, **(details or {})},
    )


def _opened(keyring: Keyring, customer: Customer, project: Project) -> dict[str, Any]:
    return keyring.sealer(customer).open("project", project.id, project.sealed)


def _sealed(keyring: Keyring, customer: Customer, project: Project, name: str,
            start: date | None, end: date | None) -> bytes:
    return keyring.sealer(customer).seal("project", project.id, {
        "name": name,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
    })


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def sees(db: Session, user_id: int, roles: set[Role], project: Project) -> bool:
    """Whether someone who sees the customer fully may open this project."""
    return (not on_team_only(project) or "all" in sights(roles)
            or user_id in team_ids(db, project))


def _visible(db: Session, request: Request, record: UserSession, project_id: int
             ) -> tuple[Project, Customer]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    customer, _ = visible_customer(db, request, record, project.customer_id)
    if not sees(db, record.user_id, roles_of(db, record.user_id), project):
        _log(db, request, record, "project.access_denied", project)
        db.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return project, customer


def _named_user(db: Session, user_id: int | None) -> Named | None:
    user = db.get(User, user_id) if user_id else None
    return Named(id=user.id, name=user.display_name) if user else None


def _summary(db: Session, keyring: Keyring, project: Project, customer: Customer
             ) -> ProjectSummary:
    opened = _opened(keyring, customer, project)
    return ProjectSummary(
        id=project.id, number=project.number, name=opened["name"],
        customer=Named(id=customer.id, name=keyring.name(customer)),
        responsible=_named_user(db, project.responsible_id),
        reviewer=_named_user(db, project.reviewer_id),
        start_date=_date(opened["start_date"]), end_date=_date(opened["end_date"]),
        classification=project.classification, archived_at=project.archived_at,
    )


def _team(db: Session, project: Project) -> list[Member]:
    ids = team_ids(db, project)
    users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.display_name))
    return [Member(id=u.id, name=u.display_name, roles=sorted(roles_of(db, u.id)),
                   responsible=u.id == project.responsible_id,
                   reviewer=u.id == project.reviewer_id) for u in users]


def _detail(db: Session, record: UserSession, keyring: Keyring, project: Project
            ) -> ProjectDetail:
    customer = db.get(Customer, project.customer_id)
    assert customer is not None
    sealer = keyring.sealer(customer)
    contacts = {c.id: c.name for c in contacts_of(db, sealer, customer.id)}
    sites = {s.id: s.name for s in sites_of(db, sealer, customer.id)}
    roles = roles_of(db, record.user_id)
    return ProjectDetail(
        **_summary(db, keyring, project, customer).model_dump(),
        contact=(Named(id=project.contact_id, name=contacts[project.contact_id])
                 if project.contact_id in contacts else None),
        sites=[Named(id=i, name=sites[i]) for i in site_ids_of(db, project.id) if i in sites],
        team=_team(db, project),
        created_at=project.created_at,
        may_edit=project.archived_at is None and may_manage_projects(roles),
        may_reopen=project.archived_at is not None and may_manage_projects(roles),
    )


def _assigned_with(db: Session, user_id: int, role: Role, customer: Customer) -> bool:
    user = db.get(User, user_id)
    return (user is not None and user.is_active and role in roles_of(db, user_id)
            and is_assigned(db, user_id, customer.id))


def _check_links(db: Session, customer: Customer, body: ProjectFields,
                 responsible_id: int | None, reviewer_id: int | None) -> None:
    """The contact and sites must be this customer's; the responsible person one of
    its technicians and the reviewer one of its reviewers, and never the same
    person: nobody reviews their own report."""
    if body.contact_id is not None:
        contact = db.get(CustomerContact, body.contact_id)
        if contact is None or contact.customer_id != customer.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That contact isn't this customer's.")
    for site_id in body.site_ids:
        site = db.get(CustomerSite, site_id)
        if site is None or site.customer_id != customer.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That site isn't this customer's.")
    if body.responsible_id is not None and not _assigned_with(
            db, body.responsible_id, Role.TECHNICIAN, customer):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The responsible technician must be an active technician assigned to this "
            "customer.",
        )
    if body.reviewer_id is not None and not _assigned_with(
            db, body.reviewer_id, Role.REVIEWER, customer):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The reviewer must be an active reviewer assigned to this customer.",
        )
    if responsible_id is not None and responsible_id == reviewer_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The reviewer can't be the responsible technician: nobody reviews their own "
            "report.",
        )


def _set_sites(db: Session, project: Project, site_ids: list[int]) -> None:
    db.execute(delete(ProjectSite).where(ProjectSite.project_id == project.id))
    for site_id in sorted(set(site_ids)):
        db.add(ProjectSite(project_id=project.id, site_id=site_id))


def _editable(db: Session, request: Request, record: UserSession, project_id: int
              ) -> tuple[Project, Customer]:
    project, customer = _visible(db, request, record, project_id)
    if not may_manage_projects(roles_of(db, record.user_id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only Managers and Administrators change projects.")
    if project.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Archived projects are read-only.")
    return project, customer


@router.get("/projects")
def list_my_projects(record: FullSession, db: DB) -> list[ProjectSummary]:
    """Active projects this person may open, across their customers, newest first."""
    roles = roles_of(db, record.user_id)
    query = select(Project, Customer).join(Customer).where(Project.archived_at.is_(None))
    if "all" not in sights(roles):
        query = query.where(Project.customer_id.in_(assigned_customer_ids(db, record.user_id)))
    rows = db.execute(query.order_by(Project.created_at.desc(), Project.id.desc()).limit(200))
    keyring = Keyring()
    return [_summary(db, keyring, project, customer) for project, customer in rows
            if sees(db, record.user_id, roles, project)]


@router.get("/customers/{customer_id}/projects")
def list_projects(customer_id: int, request: Request, record: FullSession, db: DB,
                  archived: bool = False) -> list[ProjectSummary]:
    customer, _ = visible_customer(db, request, record, customer_id)
    roles = roles_of(db, record.user_id)
    query = select(Project).where(
        Project.customer_id == customer.id,
        Project.archived_at.is_not(None) if archived else Project.archived_at.is_(None),
    ).order_by(Project.number.desc())
    keyring = Keyring()
    return [_summary(db, keyring, project, customer) for project in db.scalars(query)
            if sees(db, record.user_id, roles, project)]


@router.post("/customers/{customer_id}/projects")
def create_project(customer_id: int, body: ProjectIn, request: Request, record: FullSession,
                   db: DB) -> ProjectDetail:
    customer, _ = visible_customer(db, request, record, customer_id)
    if not may_manage_projects(roles_of(db, record.user_id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only Managers and Administrators start projects.")
    _check_links(db, customer, body, body.responsible_id, body.reviewer_id)
    project = Project(
        customer_id=customer.id, number=next_number(db), sealed=b"",
        responsible_id=body.responsible_id, reviewer_id=body.reviewer_id,
        contact_id=body.contact_id,
        classification=body.classification, created_at=clock.utcnow(),
        created_by=record.user_id,
    )
    db.add(project)
    db.flush()
    keyring = Keyring()
    project.sealed = _sealed(keyring, customer, project, body.name.strip(), body.start_date,
                             body.end_date)
    _set_sites(db, project, body.site_ids)
    _log(db, request, record, "project.created", project,
         {"customer": customer.id, "classification": project.classification})
    db.commit()
    return _detail(db, record, keyring, project)


@router.get("/projects/{project_id}")
def get_project(project_id: int, request: Request, record: FullSession, db: DB) -> ProjectDetail:
    project, _ = _visible(db, request, record, project_id)
    return _detail(db, record, Keyring(), project)


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, request: Request, record: FullSession,
                   db: DB) -> ProjectDetail:
    project, customer = _editable(db, request, record, project_id)
    sent = body.model_fields_set
    _check_links(
        db, customer, body,
        body.responsible_id if "responsible_id" in sent else project.responsible_id,
        body.reviewer_id if "reviewer_id" in sent else project.reviewer_id,
    )
    keyring = Keyring()
    opened = _opened(keyring, customer, project)
    name = body.name.strip() if body.name is not None else opened["name"]
    start = body.start_date if "start_date" in sent else _date(opened["start_date"])
    end = body.end_date if "end_date" in sent else _date(opened["end_date"])
    if start and end and end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The end date comes before the start date.")
    changed = [field for field, before, after in (
        ("name", opened["name"], name), ("start_date", _date(opened["start_date"]), start),
        ("end_date", _date(opened["end_date"]), end)) if before != after]
    if changed:
        project.sealed = _sealed(keyring, customer, project, name, start, end)
    for field in ("responsible_id", "reviewer_id", "contact_id", "classification"):
        if field in sent and getattr(body, field) != getattr(project, field):
            setattr(project, field, getattr(body, field))
            changed.append(field)
    if "site_ids" in sent and sorted(set(body.site_ids)) != site_ids_of(db, project.id):
        _set_sites(db, project, body.site_ids)
        changed.append("sites")
    if changed:
        _log(db, request, record, "project.updated", project, {"fields": changed})
    db.commit()
    return _detail(db, record, keyring, project)


@router.put("/projects/{project_id}/team")
def set_team(project_id: int, body: TeamUpdate, request: Request, record: FullSession, db: DB
             ) -> ProjectDetail:
    """Who's on the project besides its responsible technician and reviewer. They
    must be assigned to the customer; a TLP:RED project is for them, Administrators
    and Managers only."""
    project, customer = _editable(db, request, record, project_id)
    wanted = set(body.user_ids) - {project.responsible_id, project.reviewer_id}
    for user_id in wanted:
        user = db.get(User, user_id)
        if user is None or not user.is_active or not is_assigned(db, user_id, customer.id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Only active people assigned to this customer can be on its projects.",
            )
    current = member_ids(db, project.id)
    for user_id in sorted(wanted - current):
        db.add(ProjectMember(project_id=project.id, user_id=user_id, added_at=clock.utcnow(),
                             added_by=record.user_id))
    for user_id in sorted(current - wanted):
        db.execute(delete(ProjectMember).where(ProjectMember.project_id == project.id,
                                               ProjectMember.user_id == user_id))
    if wanted != current:
        _log(db, request, record, "project.team_changed", project, {
            "added": sorted(wanted - current), "removed": sorted(current - wanted)})
    db.commit()
    return _detail(db, record, Keyring(), project)


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: int, request: Request, record: FullSession, db: DB
                    ) -> ProjectDetail:
    project, _ = _editable(db, request, record, project_id)
    project.archived_at = clock.utcnow()
    project.archived_by = record.user_id
    _log(db, request, record, "project.archived", project)
    db.commit()
    return _detail(db, record, Keyring(), project)


@router.post("/projects/{project_id}/reopen")
def reopen_project(project_id: int, request: Request, admin: ProjectManager, db: DB
                   ) -> ProjectDetail:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if project.archived_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That project isn't archived.")
    project.archived_at = None
    project.archived_by = None
    _log(db, request, admin, "project.reopened", project)
    db.commit()
    return _detail(db, admin, Keyring(), project)
