"""The customers API: customers, their sites and contacts, who's assigned, the logo.

Creating and changing customers is for Administrators and Managers
(MANAGE_CUSTOMERS), deleting one for Administrators only; everyone else sees what
app/customers.py allows. A customer someone may not see
answers 404, the same as one that doesn't exist, and the refusal is logged.
Everything about a customer is sealed with its key and opened per request, only
for those allowed to see it; the audit log names customers by ID only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.dependencies import DB, FullSession, client_ip, require, require_step_up
from app.auth.sessions import UserSession
from app.custom_fields import merge_values, shown_values
from app.customers import (
    Customer,
    CustomerAssignment,
    CustomerContact,
    CustomerSite,
    Keyring,
    Sealer,
    Visibility,
    assigned_customer_ids,
    level_for,
    may_delete,
    may_manage,
    may_manage_projects,
    sights,
    visibility,
)
from app.images import (
    IMAGE_HEADERS,
    LOGO_SIZE,
    ImageRejected,
    clean_image,
    image_version,
    load_image,
    remove_image,
    store_image,
)
from app.projects import TEAM_ONLY, Project, ProjectMember, projects_joined
from app.roles import Capability, Role, UserRole, roles_of
from app.users import User

router = APIRouter(prefix="/customers")

Manager = Annotated[UserSession, Depends(require(Capability.MANAGE_CUSTOMERS))]
Deleter = Annotated[UserSession, Depends(require(Capability.DELETE_CUSTOMERS))]

NOT_FOUND = "That customer doesn't exist."
ORDER: dict[Visibility, int] = {"names": 0, "metadata": 1, "full": 2}


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    address: str = Field(default="", max_length=500)


class SiteOut(SiteIn):
    id: int


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=150)
    email: str = Field(default="", max_length=254, pattern=r"^([^@\s]+@[^@\s]+)?$")
    phone: str = Field(default="", max_length=50, pattern=r"^[0-9+()\-. ]*$")


class ContactOut(ContactIn):
    id: int


def _cvr(value: str | None) -> str | None:
    """A Danish CVR number: 8 digits, spaces allowed while typing. Empty for none."""
    if value is None:
        return None
    digits = value.replace(" ", "")
    if not digits:
        return None
    if not (len(digits) == 8 and digits.isdigit()):
        raise ValueError("A CVR number has 8 digits.")
    return digits


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    cvr: str | None = None
    address: str = Field(default="", max_length=1000)
    language: Literal["da", "en"] = "da"
    # Months raw data is kept after a project is archived.
    retention_months: int = Field(default=12, ge=1, le=120)
    # Custom fields' values by key (app/custom_fields.py); None or "" clears one.
    custom: dict[str, Any] = Field(default_factory=dict, max_length=100)

    _check_cvr = field_validator("cvr")(_cvr)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cvr: str | None = None
    address: str | None = Field(default=None, max_length=1000)
    language: Literal["da", "en"] | None = None
    retention_months: int | None = Field(default=None, ge=1, le=120)
    # Only the custom fields given change.
    custom: dict[str, Any] | None = Field(default=None, max_length=100)

    _check_cvr = field_validator("cvr")(_cvr)


class Person(BaseModel):
    id: int
    username: str
    display_name: str
    roles: list[Role]


class Assigned(Person):
    # What they're assigned to this customer as: technician, reviewer or both.
    assigned_as: list[Role]


class CustomerSummary(BaseModel):
    id: int
    name: str
    visibility: Visibility
    # Only with metadata or full sight.
    cvr: str | None = None
    active_projects: int | None = None
    archived_projects: int | None = None
    # Only with full sight.
    people: int | None = None
    logo_url: str | None = None


class CustomerDetail(CustomerSummary):
    # Only with full sight.
    address: str | None = None
    language: str | None = None
    retention_months: int | None = None
    created_at: datetime | None = None
    custom: dict[str, Any] | None = None
    sites: list[SiteOut] | None = None
    contacts: list[ContactOut] | None = None
    assigned: list[Assigned] | None = None
    may_manage: bool = False
    may_delete: bool = False
    may_manage_projects: bool = False
    # For a Manager or Administrator choosing who's assigned: everyone who may be.
    assignable: list[Person] | None = None


class Assignments(BaseModel):
    """Who works with the customer, as what. Someone in both lists is both."""

    technicians: list[int] = Field(default=[], max_length=500)
    reviewers: list[int] = Field(default=[], max_length=500)


class DeleteRequest(BaseModel):
    # Typed by the person deleting, so a slip of the mouse deletes nothing.
    confirm_name: str


def _log(
    db: Session, request: Request, record: UserSession, action: str, customer_id: int,
    details: dict[str, object] | None = None,
) -> None:
    audit.append(
        db, action, actor_id=record.user.id, actor_name=record.user.username,
        target_type="customer", target_id=str(customer_id), ip=client_ip(request),
        details=details,
    )


def logo_key(customer_id: int) -> str:
    return f"customer/{customer_id}/logo"


def _logo_url(db: Session, customer_id: int) -> str | None:
    version = image_version(db, logo_key(customer_id))
    return f"/api/customers/{customer_id}/logo?v={version}" if version else None


def visible_customer(
    db: Session, request: Request, record: UserSession, customer_id: int,
    need: Visibility = "full",
) -> tuple[Customer, Visibility]:
    """The customer, if this person may see at least `need` of it; else 404."""
    customer = db.get(Customer, customer_id)
    level = (
        visibility(db, record.user_id, roles_of(db, record.user_id), customer_id)
        if customer else None
    )
    if customer is None or level is None or ORDER[level] < ORDER[need]:
        if customer is not None:
            _log(db, request, record, "customer.access_denied", customer_id, {"needed": need})
            db.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return customer, level


def _project_counts(db: Session, user_id: int) -> dict[int, tuple[int, int]]:
    """Active and archived projects per customer, counting only what this person may
    open: a TLP:RED project counts for its team, Administrators and Managers. An
    auditor's overview counts them all."""
    sight = sights(roles_of(db, user_id))
    joined = projects_joined(db, user_id)
    every = bool(sight & {"all", "metadata"})
    rows = db.execute(select(Project.id, Project.customer_id, Project.archived_at,
                             Project.classification))
    counts: dict[int, list[int]] = {}
    for project_id, customer_id, archived_at, classification in rows:
        if classification == TEAM_ONLY and not every and project_id not in joined:
            continue
        counts.setdefault(customer_id, [0, 0])[0 if archived_at is None else 1] += 1
    return {k: (v[0], v[1]) for k, v in counts.items()}


def _summary(db: Session, keyring: Keyring, customer: Customer, level: Visibility,
             counts: dict[int, tuple[int, int]], people: dict[int, int]) -> dict[str, Any]:
    details = keyring.details(customer)
    fields: dict[str, Any] = {"id": customer.id, "name": details["name"], "visibility": level}
    if level != "names":
        active, archived = counts.get(customer.id, (0, 0))
        fields |= {"active_projects": active, "archived_projects": archived}
    if level == "full":
        fields |= {"cvr": details["cvr"], "logo_url": _logo_url(db, customer.id),
                   "people": people.get(customer.id, 0)}
    return fields


def _people_counts(db: Session) -> dict[int, int]:
    """How many people are assigned to each customer."""
    rows = db.execute(select(CustomerAssignment.customer_id, func.count())
                      .group_by(CustomerAssignment.customer_id))
    return {customer_id: count for customer_id, count in rows}


def _people(db: Session, user_ids: list[int]) -> list[Person]:
    if not user_ids:
        return []
    users = db.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.display_name))
    return [Person(id=u.id, username=u.username, display_name=u.display_name,
                   roles=sorted(roles_of(db, u.id))) for u in users]


def _assignable_ids(db: Session, *roles: Role) -> list[int]:
    """Active people with any of these roles (by default technicians and reviewers:
    the people assignments are for)."""
    wanted = roles or (Role.TECHNICIAN, Role.REVIEWER)
    return list(db.scalars(
        select(UserRole.user_id).join(User, User.id == UserRole.user_id)
        .where(UserRole.role.in_([r.value for r in wanted]), User.is_active)
        .distinct()
    ))


def sites_of(db: Session, sealer: Sealer, customer_id: int) -> list[SiteOut]:
    sites = db.scalars(select(CustomerSite).where(CustomerSite.customer_id == customer_id))
    found = [SiteOut(id=s.id, **sealer.open("site", s.id, s.sealed)) for s in sites]
    return sorted(found, key=lambda s: s.name.casefold())


def contacts_of(db: Session, sealer: Sealer, customer_id: int) -> list[ContactOut]:
    contacts = db.scalars(
        select(CustomerContact).where(CustomerContact.customer_id == customer_id)
    )
    found = [ContactOut(id=c.id, **sealer.open("contact", c.id, c.sealed)) for c in contacts]
    return sorted(found, key=lambda c: c.name.casefold())


def _detail(db: Session, record: UserSession, keyring: Keyring, customer: Customer,
            level: Visibility) -> CustomerDetail:
    summary = _summary(db, keyring, customer, level, _project_counts(db, record.user_id),
                       _people_counts(db))
    if level != "full":
        return CustomerDetail(**summary)
    roles = roles_of(db, record.user_id)
    sealer = keyring.sealer(customer)
    held = {a.user_id: a for a in db.scalars(
        select(CustomerAssignment).where(CustomerAssignment.customer_id == customer.id))}
    assigned = [Assigned(**person.model_dump(), assigned_as=held[person.id].capacities())
                for person in _people(db, list(held))]
    manage = may_manage(roles)
    details = keyring.details(customer)
    return CustomerDetail(
        **summary,
        address=details["address"],
        custom=shown_values(db, "customer", details.get("custom")),
        language=customer.language,
        retention_months=customer.retention_months,
        created_at=customer.created_at,
        sites=sites_of(db, sealer, customer.id),
        contacts=contacts_of(db, sealer, customer.id),
        assigned=assigned,
        may_manage=manage,
        may_delete=may_delete(roles),
        may_manage_projects=may_manage_projects(roles),
        assignable=_people(db, _assignable_ids(db)) if manage else None,
    )


# Customers


@router.get("")
def list_customers(record: FullSession, db: DB, q: str = "") -> list[CustomerSummary]:
    """The customers this person sees, by name; q searches names and CVR numbers.
    Names are sealed, so the search runs here, over the opened ones."""
    sight = sights(roles_of(db, record.user_id))
    assigned = assigned_customer_ids(db, record.user_id)
    counts = _project_counts(db, record.user_id)
    people = _people_counts(db)
    keyring = Keyring()
    needle = q.strip().casefold().replace(" ", "")
    found = []
    for customer in db.scalars(select(Customer)):
        level = level_for(sight, customer.id in assigned)
        if level is None:
            continue
        summary = CustomerSummary(**_summary(db, keyring, customer, level, counts, people))
        details = keyring.details(customer)
        haystack = (details["name"] + " " + (details["cvr"] or "")).casefold().replace(" ", "")
        if needle in haystack:
            found.append(summary)
    return sorted(found, key=lambda c: c.name.casefold())


@router.post("")
def create_customer(body: CustomerIn, request: Request, admin: Manager, db: DB) -> CustomerDetail:
    customer = Customer(
        wrapped_key=b"", sealed=b"", language=body.language,
        retention_months=body.retention_months, created_at=clock.utcnow(),
        created_by=admin.user_id,
    )
    db.add(customer)
    db.flush()  # the key is bound to the customer's ID
    keyring = Keyring()
    custom = merge_values(db, "customer", None, body.custom)
    customer.sealed = keyring.give_new_key(customer).seal("customer", customer.id, {
        "name": body.name.strip(), "cvr": body.cvr, "address": body.address.strip(),
        "custom": custom,
    })
    _log(db, request, admin, "customer.created", customer.id)
    db.commit()
    return _detail(db, admin, keyring, customer, "full")


@router.get("/{customer_id}")
def get_customer(customer_id: int, request: Request, record: FullSession, db: DB
                 ) -> CustomerDetail:
    customer, level = visible_customer(db, request, record, customer_id, need="names")
    return _detail(db, record, Keyring(), customer, level)


@router.patch("/{customer_id}")
def update_customer(customer_id: int, body: CustomerUpdate, request: Request, admin: Manager,
                    db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    keyring = Keyring()
    details = dict(keyring.details(customer))
    changed: list[str] = []
    wanted = {
        "name": body.name.strip() if body.name is not None else details["name"],
        "cvr": body.cvr if "cvr" in body.model_fields_set else details["cvr"],
        "address": body.address.strip() if body.address is not None else details["address"],
        "custom": (merge_values(db, "customer", details.get("custom"), body.custom)
                   if body.custom is not None else details.get("custom", {})),
    }
    before = {"custom": {}, **details}
    if wanted != before:
        changed += sorted(name for name in wanted if wanted[name] != before[name])
        customer.sealed = keyring.sealer(customer).seal("customer", customer.id, wanted)
    for field in ("language", "retention_months"):
        value = getattr(body, field)
        if value is not None and value != getattr(customer, field):
            setattr(customer, field, value)
            changed.append(field)
    if changed:
        _log(db, request, admin, "customer.updated", customer.id, {"fields": changed})
    db.commit()
    return _detail(db, admin, keyring, customer, "full")


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, body: Annotated[DeleteRequest, Body()], request: Request,
                    admin: Deleter, db: DB) -> None:
    """Delete a customer and everything under it. Its key goes with it, so whatever
    was sealed with it is unreadable from then on (crypto-shredding)."""
    customer, _ = visible_customer(db, request, admin, customer_id)
    if body.confirm_name.strip() != Keyring().name(customer):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Type the customer's name exactly to confirm.")
    require_step_up(admin)
    projects = db.scalar(select(func.count()).select_from(Project)
                         .where(Project.customer_id == customer.id)) or 0
    remove_image(db, logo_key(customer.id))
    db.delete(customer)
    _log(db, request, admin, "customer.deleted", customer_id, {"projects": projects})
    db.commit()


# Sites and contacts. Both are sealed; the audit log names them by ID only.


def _site(db: Session, customer: Customer, site_id: int) -> CustomerSite:
    site = db.get(CustomerSite, site_id)
    if site is None or site.customer_id != customer.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That site doesn't exist.")
    return site


def _site_fields(body: SiteIn) -> dict[str, str]:
    return {"name": body.name.strip(), "address": body.address.strip()}


@router.post("/{customer_id}/sites")
def add_site(customer_id: int, body: SiteIn, request: Request, admin: Manager, db: DB
             ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    keyring = Keyring()
    site = CustomerSite(customer_id=customer.id, sealed=b"")
    db.add(site)
    db.flush()
    site.sealed = keyring.sealer(customer).seal("site", site.id, _site_fields(body))
    _log(db, request, admin, "customer.site_added", customer.id, {"site": site.id})
    db.commit()
    return _detail(db, admin, keyring, customer, "full")


@router.put("/{customer_id}/sites/{site_id}")
def update_site(customer_id: int, site_id: int, body: SiteIn, request: Request, admin: Manager,
                db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    keyring = Keyring()
    site = _site(db, customer, site_id)
    site.sealed = keyring.sealer(customer).seal("site", site.id, _site_fields(body))
    _log(db, request, admin, "customer.site_changed", customer.id, {"site": site.id})
    db.commit()
    return _detail(db, admin, keyring, customer, "full")


@router.delete("/{customer_id}/sites/{site_id}")
def remove_site(customer_id: int, site_id: int, request: Request, admin: Manager, db: DB
                ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    db.delete(_site(db, customer, site_id))
    _log(db, request, admin, "customer.site_removed", customer.id, {"site": site_id})
    db.commit()
    return _detail(db, admin, Keyring(), customer, "full")


def _contact(db: Session, customer: Customer, contact_id: int) -> CustomerContact:
    contact = db.get(CustomerContact, contact_id)
    if contact is None or contact.customer_id != customer.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That contact doesn't exist.")
    return contact


def _contact_fields(body: ContactIn) -> dict[str, str]:
    return {name: getattr(body, name).strip() for name in ("name", "role", "email", "phone")}


@router.post("/{customer_id}/contacts")
def add_contact(customer_id: int, body: ContactIn, request: Request, admin: Manager, db: DB
                ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    keyring = Keyring()
    contact = CustomerContact(customer_id=customer.id, sealed=b"")
    db.add(contact)
    db.flush()
    contact.sealed = keyring.sealer(customer).seal("contact", contact.id, _contact_fields(body))
    _log(db, request, admin, "customer.contact_added", customer.id, {"contact": contact.id})
    db.commit()
    return _detail(db, admin, keyring, customer, "full")


@router.put("/{customer_id}/contacts/{contact_id}")
def update_contact(customer_id: int, contact_id: int, body: ContactIn, request: Request,
                   admin: Manager, db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    keyring = Keyring()
    contact = _contact(db, customer, contact_id)
    contact.sealed = keyring.sealer(customer).seal("contact", contact.id, _contact_fields(body))
    _log(db, request, admin, "customer.contact_changed", customer.id, {"contact": contact.id})
    db.commit()
    return _detail(db, admin, keyring, customer, "full")


@router.delete("/{customer_id}/contacts/{contact_id}")
def remove_contact(customer_id: int, contact_id: int, request: Request, admin: Manager, db: DB
                   ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    db.delete(_contact(db, customer, contact_id))
    _log(db, request, admin, "customer.contact_removed", customer.id, {"contact": contact_id})
    db.commit()
    return _detail(db, admin, Keyring(), customer, "full")


# Who's assigned


BOTH = frozenset({Role.TECHNICIAN, Role.REVIEWER})


def _leave_projects(db: Session, customer_id: int, user_id: int,
                    dropped: frozenset[Role] = BOTH) -> int:
    """Take someone off a customer's projects in what they're no longer assigned
    as: as technician, the responsible technician and technician team member; as
    reviewer, the reviewer and reviewer team member. Returns how many projects."""
    projects = list(db.scalars(select(Project).where(Project.customer_id == customer_id)))
    left = 0
    for project in projects:
        on = False
        member = db.get(ProjectMember, (project.id, user_id))
        if member is not None and Role(member.as_role) in dropped:
            db.delete(member)
            on = True
        if Role.TECHNICIAN in dropped and project.responsible_id == user_id:
            project.responsible_id = None
            on = True
        if Role.REVIEWER in dropped and project.reviewer_id == user_id:
            project.reviewer_id = None
            on = True
        left += on
    return left


@router.put("/{customer_id}/assignments")
def set_assignments(customer_id: int, body: Assignments, request: Request, admin: Manager,
                    db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    technicians, reviewers = set(body.technicians), set(body.reviewers)
    if (not technicians <= set(_assignable_ids(db, Role.TECHNICIAN))
            or not reviewers <= set(_assignable_ids(db, Role.REVIEWER))):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only active technicians can be assigned as technicians, and active reviewers as "
            "reviewers.",
        )
    current = {a.user_id: a for a in db.scalars(
        select(CustomerAssignment).where(CustomerAssignment.customer_id == customer.id))}
    everyone = technicians | reviewers | set(current)
    usernames = {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(everyone)))}
    for user_id in sorted(everyone):
        as_technician, as_reviewer = user_id in technicians, user_id in reviewers
        held = current.get(user_id)
        details: dict[str, object] = {"user": usernames.get(user_id)}
        if held is None:
            held = CustomerAssignment(customer_id=customer.id, user_id=user_id,
                                      assigned_at=clock.utcnow(), assigned_by=admin.user_id,
                                      as_technician=as_technician, as_reviewer=as_reviewer)
            db.add(held)
            _log(db, request, admin, "customer.assigned", customer.id,
                 details | {"as": held.capacities()})
        elif not (as_technician or as_reviewer):
            db.delete(held)
            _log(db, request, admin, "customer.unassigned", customer.id,
                 details | {"projects_left": _leave_projects(db, customer.id, user_id)})
        elif (held.as_technician, held.as_reviewer) != (as_technician, as_reviewer):
            dropped = frozenset(role for role, before, after in (
                (Role.TECHNICIAN, held.as_technician, as_technician),
                (Role.REVIEWER, held.as_reviewer, as_reviewer)) if before and not after)
            held.as_technician, held.as_reviewer = as_technician, as_reviewer
            left = _leave_projects(db, customer.id, user_id, dropped) if dropped else 0
            _log(db, request, admin, "customer.assignment_changed", customer.id,
                 details | {"as": held.capacities(), "projects_left": left})
    db.commit()
    return _detail(db, admin, Keyring(), customer, "full")


# Logo


@router.put("/{customer_id}/logo")
def upload_logo(
    customer_id: int, data: Annotated[bytes, Body(media_type="application/octet-stream")],
    request: Request, admin: Manager, db: DB,
) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    try:
        png = clean_image(data, max_size=LOGO_SIZE)
    except ImageRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    store_image(db, logo_key(customer.id), png)
    _log(db, request, admin, "customer.logo_changed", customer.id)
    db.commit()
    return _detail(db, admin, Keyring(), customer, "full")


@router.delete("/{customer_id}/logo")
def remove_logo(customer_id: int, request: Request, admin: Manager, db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    if remove_image(db, logo_key(customer.id)):
        _log(db, request, admin, "customer.logo_removed", customer.id)
    db.commit()
    return _detail(db, admin, Keyring(), customer, "full")


@router.get("/{customer_id}/logo")
def get_logo(customer_id: int, request: Request, record: FullSession, db: DB) -> Response:
    visible_customer(db, request, record, customer_id)
    image = load_image(db, logo_key(customer_id))
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo is set.")
    return Response(image.data, media_type=image.content_type, headers=IMAGE_HEADERS)
