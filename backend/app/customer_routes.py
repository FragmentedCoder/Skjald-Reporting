"""The customers API: customers, their sites and contacts, who's assigned, the logo.

Creating and changing customers is for Administrators (MANAGE_CUSTOMERS);
everyone else sees what app/customers.py allows. A customer someone may not see
answers 404, the same as one that doesn't exist, and the refusal is logged.
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
from app.customers import (
    Customer,
    CustomerAssignment,
    CustomerContact,
    CustomerSite,
    Sealer,
    Visibility,
    assigned_customer_ids,
    give_new_key,
    level_for,
    may_create_projects,
    may_manage,
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
from app.projects import Project
from app.roles import Capability, Role, UserRole, roles_of
from app.users import User

router = APIRouter(prefix="/customers")

Manager = Annotated[UserSession, Depends(require(Capability.MANAGE_CUSTOMERS))]

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

    _check_cvr = field_validator("cvr")(_cvr)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cvr: str | None = None
    address: str | None = Field(default=None, max_length=1000)
    language: Literal["da", "en"] | None = None
    retention_months: int | None = Field(default=None, ge=1, le=120)

    _check_cvr = field_validator("cvr")(_cvr)


class Person(BaseModel):
    id: int
    username: str
    display_name: str
    roles: list[Role]


class CustomerSummary(BaseModel):
    id: int
    name: str
    visibility: Visibility
    # Only with metadata or full sight.
    cvr: str | None = None
    active_projects: int | None = None
    archived_projects: int | None = None
    logo_url: str | None = None


class CustomerDetail(CustomerSummary):
    # Only with full sight.
    address: str | None = None
    language: str | None = None
    retention_months: int | None = None
    created_at: datetime | None = None
    sites: list[SiteOut] | None = None
    contacts: list[ContactOut] | None = None
    assigned: list[Person] | None = None
    may_manage: bool = False
    may_create_projects: bool = False
    # For an Administrator choosing who's assigned: everyone who may be.
    assignable: list[Person] | None = None


class Assignments(BaseModel):
    user_ids: list[int] = Field(max_length=500)


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


def _project_counts(db: Session) -> dict[int, tuple[int, int]]:
    rows = db.execute(
        select(Project.customer_id, Project.archived_at.is_(None), func.count())
        .group_by(Project.customer_id, Project.archived_at.is_(None))
    )
    counts: dict[int, list[int]] = {}
    for customer_id, active, count in rows:
        counts.setdefault(customer_id, [0, 0])[0 if active else 1] += count
    return {k: (v[0], v[1]) for k, v in counts.items()}


def _summary(db: Session, customer: Customer, level: Visibility,
             counts: dict[int, tuple[int, int]]) -> dict[str, Any]:
    fields: dict[str, Any] = {"id": customer.id, "name": customer.name, "visibility": level}
    if level != "names":
        active, archived = counts.get(customer.id, (0, 0))
        fields |= {"active_projects": active, "archived_projects": archived}
    if level == "full":
        fields |= {"cvr": customer.cvr, "logo_url": _logo_url(db, customer.id)}
    return fields


def _people(db: Session, user_ids: list[int]) -> list[Person]:
    if not user_ids:
        return []
    users = db.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.display_name))
    return [Person(id=u.id, username=u.username, display_name=u.display_name,
                   roles=sorted(roles_of(db, u.id))) for u in users]


def _assignable_ids(db: Session) -> list[int]:
    """Active technicians and reviewers: the people assignments are for."""
    return list(db.scalars(
        select(UserRole.user_id).join(User, User.id == UserRole.user_id)
        .where(UserRole.role.in_([Role.TECHNICIAN.value, Role.REVIEWER.value]), User.is_active)
        .distinct()
    ))


def sites_of(db: Session, sealer: Sealer, customer_id: int) -> list[SiteOut]:
    sites = db.scalars(
        select(CustomerSite).where(CustomerSite.customer_id == customer_id)
        .order_by(CustomerSite.name)
    )
    return [SiteOut(id=s.id, name=s.name, **sealer.open("site", s.id, s.sealed)) for s in sites]


def contacts_of(db: Session, sealer: Sealer, customer_id: int) -> list[ContactOut]:
    contacts = db.scalars(
        select(CustomerContact).where(CustomerContact.customer_id == customer_id)
        .order_by(CustomerContact.id)
    )
    found = [ContactOut(id=c.id, **sealer.open("contact", c.id, c.sealed)) for c in contacts]
    return sorted(found, key=lambda c: c.name.casefold())


def _detail(db: Session, record: UserSession, customer: Customer,
            level: Visibility) -> CustomerDetail:
    summary = _summary(db, customer, level, _project_counts(db))
    if level != "full":
        return CustomerDetail(**summary)
    roles = roles_of(db, record.user_id)
    sealer = Sealer(customer)
    assigned = list(db.scalars(
        select(CustomerAssignment.user_id).where(CustomerAssignment.customer_id == customer.id)
    ))
    manage = may_manage(roles)
    return CustomerDetail(
        **summary,
        address=sealer.open("customer", customer.id, customer.sealed)["address"],
        language=customer.language,
        retention_months=customer.retention_months,
        created_at=customer.created_at,
        sites=sites_of(db, sealer, customer.id),
        contacts=contacts_of(db, sealer, customer.id),
        assigned=_people(db, assigned),
        may_manage=manage,
        may_create_projects=may_create_projects(db, record.user_id, roles, customer.id),
        assignable=_people(db, _assignable_ids(db)) if manage else None,
    )


# Customers


@router.get("")
def list_customers(record: FullSession, db: DB, q: str = "") -> list[CustomerSummary]:
    sight = sights(roles_of(db, record.user_id))
    assigned = assigned_customer_ids(db, record.user_id)
    query = select(Customer).order_by(Customer.name)
    if q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(Customer.name.ilike(pattern) | Customer.cvr.ilike(pattern))
    counts = _project_counts(db)
    found = []
    for customer in db.scalars(query):
        level = level_for(sight, customer.id in assigned)
        if level is not None:
            found.append(CustomerSummary(**_summary(db, customer, level, counts)))
    return found


@router.post("")
def create_customer(body: CustomerIn, request: Request, admin: Manager, db: DB) -> CustomerDetail:
    customer = Customer(
        name=body.name.strip(), cvr=body.cvr, wrapped_key=b"", sealed=b"",
        language=body.language, retention_months=body.retention_months,
        created_at=clock.utcnow(), created_by=admin.user_id,
    )
    db.add(customer)
    db.flush()  # the key is bound to the customer's ID
    give_new_key(customer)
    customer.sealed = Sealer(customer).seal(
        "customer", customer.id, {"address": body.address.strip()}
    )
    _log(db, request, admin, "customer.created", customer.id, {"name": customer.name})
    db.commit()
    return _detail(db, admin, customer, "full")


@router.get("/{customer_id}")
def get_customer(customer_id: int, request: Request, record: FullSession, db: DB
                 ) -> CustomerDetail:
    customer, level = visible_customer(db, request, record, customer_id, need="names")
    return _detail(db, record, customer, level)


@router.patch("/{customer_id}")
def update_customer(customer_id: int, body: CustomerUpdate, request: Request, admin: Manager,
                    db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    changed: list[str] = []
    details: dict[str, object] = {}
    sent = body.model_fields_set
    if body.name is not None and body.name.strip() != customer.name:
        details["name"] = [customer.name, body.name.strip()]
        customer.name = body.name.strip()
        changed.append("name")
    if "cvr" in sent and body.cvr != customer.cvr:
        customer.cvr = body.cvr
        changed.append("cvr")
    for field in ("language", "retention_months"):
        value = getattr(body, field)
        if value is not None and value != getattr(customer, field):
            setattr(customer, field, value)
            changed.append(field)
    if body.address is not None:
        sealer = Sealer(customer)
        address = body.address.strip()
        if sealer.open("customer", customer.id, customer.sealed)["address"] != address:
            customer.sealed = sealer.seal("customer", customer.id, {"address": address})
            changed.append("address")
    if changed:
        _log(db, request, admin, "customer.updated", customer.id, {"fields": changed, **details})
    db.commit()
    return _detail(db, admin, customer, "full")


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, body: Annotated[DeleteRequest, Body()], request: Request,
                    admin: Manager, db: DB) -> None:
    """Delete a customer and everything under it. Its key goes with it, so whatever
    was sealed with it is unreadable from then on (crypto-shredding)."""
    customer, _ = visible_customer(db, request, admin, customer_id)
    if body.confirm_name.strip() != customer.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Type the customer's name exactly to confirm.")
    require_step_up(admin)
    projects = db.scalar(select(func.count()).select_from(Project)
                         .where(Project.customer_id == customer.id)) or 0
    remove_image(db, logo_key(customer.id))
    db.delete(customer)
    _log(db, request, admin, "customer.deleted", customer_id,
         {"name": customer.name, "projects": projects})
    db.commit()


# Sites and contacts


@router.post("/{customer_id}/sites")
def add_site(customer_id: int, body: SiteIn, request: Request, admin: Manager, db: DB
             ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    site = CustomerSite(customer_id=customer.id, name=body.name.strip(), sealed=b"")
    db.add(site)
    db.flush()
    site.sealed = Sealer(customer).seal("site", site.id, {"address": body.address.strip()})
    _log(db, request, admin, "customer.site_added", customer.id, {"site": site.id})
    db.commit()
    return _detail(db, admin, customer, "full")


def _site(db: Session, customer: Customer, site_id: int) -> CustomerSite:
    site = db.get(CustomerSite, site_id)
    if site is None or site.customer_id != customer.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That site doesn't exist.")
    return site


@router.put("/{customer_id}/sites/{site_id}")
def update_site(customer_id: int, site_id: int, body: SiteIn, request: Request, admin: Manager,
                db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    site = _site(db, customer, site_id)
    site.name = body.name.strip()
    site.sealed = Sealer(customer).seal("site", site.id, {"address": body.address.strip()})
    _log(db, request, admin, "customer.site_changed", customer.id, {"site": site.id})
    db.commit()
    return _detail(db, admin, customer, "full")


@router.delete("/{customer_id}/sites/{site_id}")
def remove_site(customer_id: int, site_id: int, request: Request, admin: Manager, db: DB
                ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    db.delete(_site(db, customer, site_id))
    _log(db, request, admin, "customer.site_removed", customer.id, {"site": site_id})
    db.commit()
    return _detail(db, admin, customer, "full")


def _contact(db: Session, customer: Customer, contact_id: int) -> CustomerContact:
    contact = db.get(CustomerContact, contact_id)
    if contact is None or contact.customer_id != customer.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That contact doesn't exist.")
    return contact


def _contact_fields(body: ContactIn) -> dict[str, str]:
    return {name: getattr(body, name).strip() for name in ("name", "role", "email", "phone")}


# Contacts are personal data: the audit log names them by ID only, so deleting the
# customer leaves nothing about them behind.


@router.post("/{customer_id}/contacts")
def add_contact(customer_id: int, body: ContactIn, request: Request, admin: Manager, db: DB
                ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    contact = CustomerContact(customer_id=customer.id, sealed=b"")
    db.add(contact)
    db.flush()
    contact.sealed = Sealer(customer).seal("contact", contact.id, _contact_fields(body))
    _log(db, request, admin, "customer.contact_added", customer.id, {"contact": contact.id})
    db.commit()
    return _detail(db, admin, customer, "full")


@router.put("/{customer_id}/contacts/{contact_id}")
def update_contact(customer_id: int, contact_id: int, body: ContactIn, request: Request,
                   admin: Manager, db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    contact = _contact(db, customer, contact_id)
    contact.sealed = Sealer(customer).seal("contact", contact.id, _contact_fields(body))
    _log(db, request, admin, "customer.contact_changed", customer.id, {"contact": contact.id})
    db.commit()
    return _detail(db, admin, customer, "full")


@router.delete("/{customer_id}/contacts/{contact_id}")
def remove_contact(customer_id: int, contact_id: int, request: Request, admin: Manager, db: DB
                   ) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    db.delete(_contact(db, customer, contact_id))
    _log(db, request, admin, "customer.contact_removed", customer.id, {"contact": contact_id})
    db.commit()
    return _detail(db, admin, customer, "full")


# Who's assigned


@router.put("/{customer_id}/assignments")
def set_assignments(customer_id: int, body: Assignments, request: Request, admin: Manager,
                    db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    wanted = set(body.user_ids)
    if not wanted <= set(_assignable_ids(db)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only active technicians and reviewers can be assigned to a customer.",
        )
    current = set(db.scalars(
        select(CustomerAssignment.user_id).where(CustomerAssignment.customer_id == customer.id)
    ))
    for user_id in sorted(wanted - current):
        db.add(CustomerAssignment(customer_id=customer.id, user_id=user_id,
                                  assigned_at=clock.utcnow(), assigned_by=admin.user_id))
    for user_id in sorted(current - wanted):
        held = db.get(CustomerAssignment, (customer.id, user_id))
        if held is not None:
            db.delete(held)
    usernames = {u.id: u.username for u in db.scalars(select(User).where(
        User.id.in_(wanted ^ current)))}
    for action, ids in (("customer.assigned", wanted - current),
                        ("customer.unassigned", current - wanted)):
        for user_id in sorted(ids):
            _log(db, request, admin, action, customer.id, {"user": usernames.get(user_id)})
    db.commit()
    return _detail(db, admin, customer, "full")


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
    return _detail(db, admin, customer, "full")


@router.delete("/{customer_id}/logo")
def remove_logo(customer_id: int, request: Request, admin: Manager, db: DB) -> CustomerDetail:
    customer, _ = visible_customer(db, request, admin, customer_id)
    if remove_image(db, logo_key(customer.id)):
        _log(db, request, admin, "customer.logo_removed", customer.id)
    db.commit()
    return _detail(db, admin, customer, "full")


@router.get("/{customer_id}/logo")
def get_logo(customer_id: int, request: Request, record: FullSession, db: DB) -> Response:
    visible_customer(db, request, record, customer_id)
    image = load_image(db, logo_key(customer_id))
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo is set.")
    return Response(image.data, media_type=image.content_type, headers=IMAGE_HEADERS)
