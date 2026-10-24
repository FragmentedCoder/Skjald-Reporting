"""The projects API.

Anyone who sees a customer fully sees its projects. Administrators and the
technicians assigned to a customer create and change them; an archived project
is read-only, and only an Administrator can reopen it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

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
    Sealer,
    assigned_customer_ids,
    is_assigned,
    may_create_projects,
    may_manage,
    sights,
)
from app.projects import (
    DEFAULT_CLASSIFICATION,
    Classification,
    Project,
    ProjectSite,
    next_number,
    site_ids_of,
)
from app.roles import Capability, Role, roles_of
from app.users import User

router = APIRouter()

Manager = Annotated[UserSession, Depends(require(Capability.MANAGE_CUSTOMERS))]


class ProjectFields(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    responsible_id: int | None = None
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


class Named(BaseModel):
    id: int
    name: str


class ProjectSummary(BaseModel):
    id: int
    number: str
    name: str
    customer: Named
    responsible: Named | None
    start_date: date | None
    end_date: date | None
    classification: str
    archived_at: datetime | None


class ProjectDetail(ProjectSummary):
    contact: Named | None
    sites: list[Named]
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


def _named_user(db: Session, user_id: int | None) -> Named | None:
    user = db.get(User, user_id) if user_id else None
    return Named(id=user.id, name=user.display_name) if user else None


def _summary(db: Session, project: Project, customer: Customer) -> ProjectSummary:
    return ProjectSummary(
        id=project.id, number=project.number, name=project.name,
        customer=Named(id=customer.id, name=customer.name),
        responsible=_named_user(db, project.responsible_id),
        start_date=project.start_date, end_date=project.end_date,
        classification=project.classification, archived_at=project.archived_at,
    )


def _detail(db: Session, record: UserSession, project: Project) -> ProjectDetail:
    customer = db.get(Customer, project.customer_id)
    assert customer is not None
    sealer = Sealer(customer)
    contacts = {c.id: c.name for c in contacts_of(db, sealer, customer.id)}
    sites = {s.id: s.name for s in sites_of(db, sealer, customer.id)}
    roles = roles_of(db, record.user_id)
    return ProjectDetail(
        **_summary(db, project, customer).model_dump(),
        contact=(Named(id=project.contact_id, name=contacts[project.contact_id])
                 if project.contact_id in contacts else None),
        sites=[Named(id=i, name=sites[i]) for i in site_ids_of(db, project.id) if i in sites],
        created_at=project.created_at,
        may_edit=project.archived_at is None
        and may_create_projects(db, record.user_id, roles, customer.id),
        may_reopen=project.archived_at is not None and may_manage(roles),
    )


def _check_links(db: Session, customer: Customer, body: ProjectFields) -> None:
    """The contact and sites must be this customer's; the responsible person one of
    its technicians."""
    if body.contact_id is not None:
        contact = db.get(CustomerContact, body.contact_id)
        if contact is None or contact.customer_id != customer.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That contact isn't this customer's.")
    for site_id in body.site_ids:
        site = db.get(CustomerSite, site_id)
        if site is None or site.customer_id != customer.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That site isn't this customer's.")
    if body.responsible_id is not None:
        user = db.get(User, body.responsible_id)
        roles = roles_of(db, body.responsible_id) if user else set()
        if (user is None or not user.is_active or Role.TECHNICIAN not in roles
                or not is_assigned(db, user.id, customer.id)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "The responsible technician must be an active technician assigned to this "
                "customer.",
            )


def _set_sites(db: Session, project: Project, site_ids: list[int]) -> None:
    db.execute(delete(ProjectSite).where(ProjectSite.project_id == project.id))
    for site_id in sorted(set(site_ids)):
        db.add(ProjectSite(project_id=project.id, site_id=site_id))


def _editable(db: Session, request: Request, record: UserSession, project_id: int
              ) -> tuple[Project, Customer]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That project doesn't exist.")
    customer, _ = visible_customer(db, request, record, project.customer_id)
    if not may_create_projects(db, record.user_id, roles_of(db, record.user_id), customer.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change this customer's projects.")
    if project.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Archived projects are read-only.")
    return project, customer


@router.get("/projects")
def list_my_projects(record: FullSession, db: DB) -> list[ProjectSummary]:
    """Active projects for the customers this person sees fully, newest first."""
    query = select(Project, Customer).join(Customer).where(Project.archived_at.is_(None))
    if "all" not in sights(roles_of(db, record.user_id)):
        query = query.where(Project.customer_id.in_(assigned_customer_ids(db, record.user_id)))
    rows = db.execute(query.order_by(Project.created_at.desc(), Project.id.desc()).limit(100))
    return [_summary(db, project, customer) for project, customer in rows]


@router.get("/customers/{customer_id}/projects")
def list_projects(customer_id: int, request: Request, record: FullSession, db: DB,
                  archived: bool = False) -> list[ProjectSummary]:
    customer, _ = visible_customer(db, request, record, customer_id)
    query = select(Project).where(
        Project.customer_id == customer.id,
        Project.archived_at.is_not(None) if archived else Project.archived_at.is_(None),
    ).order_by(Project.number.desc())
    return [_summary(db, project, customer) for project in db.scalars(query)]


@router.post("/customers/{customer_id}/projects")
def create_project(customer_id: int, body: ProjectIn, request: Request, record: FullSession,
                   db: DB) -> ProjectDetail:
    customer, _ = visible_customer(db, request, record, customer_id)
    if not may_create_projects(db, record.user_id, roles_of(db, record.user_id), customer.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "You can't create projects for this customer.")
    _check_links(db, customer, body)
    project = Project(
        customer_id=customer.id, number=next_number(db), name=body.name.strip(),
        start_date=body.start_date, end_date=body.end_date, responsible_id=body.responsible_id,
        contact_id=body.contact_id, classification=body.classification,
        created_at=clock.utcnow(), created_by=record.user_id,
    )
    db.add(project)
    db.flush()
    _set_sites(db, project, body.site_ids)
    _log(db, request, record, "project.created", project, {"customer": customer.id})
    db.commit()
    return _detail(db, record, project)


@router.get("/projects/{project_id}")
def get_project(project_id: int, request: Request, record: FullSession, db: DB) -> ProjectDetail:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That project doesn't exist.")
    visible_customer(db, request, record, project.customer_id)
    return _detail(db, record, project)


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, request: Request, record: FullSession,
                   db: DB) -> ProjectDetail:
    project, customer = _editable(db, request, record, project_id)
    sent = body.model_fields_set
    _check_links(db, customer, body)
    changed = []
    if body.name is not None and body.name.strip() != project.name:
        project.name = body.name.strip()
        changed.append("name")
    for field in ("start_date", "end_date", "responsible_id", "contact_id", "classification"):
        if field in sent and getattr(body, field) != getattr(project, field):
            setattr(project, field, getattr(body, field))
            changed.append(field)
    if project.start_date and project.end_date and project.end_date < project.start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The end date comes before the start date.")
    if "site_ids" in sent and sorted(set(body.site_ids)) != site_ids_of(db, project.id):
        _set_sites(db, project, body.site_ids)
        changed.append("sites")
    if changed:
        _log(db, request, record, "project.updated", project, {"fields": changed})
    db.commit()
    return _detail(db, record, project)


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: int, request: Request, record: FullSession, db: DB
                    ) -> ProjectDetail:
    project, _ = _editable(db, request, record, project_id)
    project.archived_at = clock.utcnow()
    project.archived_by = record.user_id
    _log(db, request, record, "project.archived", project)
    db.commit()
    return _detail(db, record, project)


@router.post("/projects/{project_id}/reopen")
def reopen_project(project_id: int, request: Request, admin: Manager, db: DB) -> ProjectDetail:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That project doesn't exist.")
    if project.archived_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That project isn't archived.")
    project.archived_at = None
    project.archived_by = None
    _log(db, request, admin, "project.reopened", project)
    db.commit()
    return _detail(db, admin, project)
