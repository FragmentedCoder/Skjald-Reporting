"""Customers: the records everything else hangs off (see docs/architecture.md).

Each customer gets its own 256-bit key when it's created, kept wrapped by the
master key and bound to the customer's ID. Addresses and contact details are
sealed with it (app/crypto/sealing.py); the name and CVR stay plain, for lists
and search. Deleting a customer deletes its key with it, so nothing sealed with
it can be read again (crypto-shredding).

Who sees which customers follows the spec's access table: Administrators all of
them, technicians and reviewers the ones they're assigned to, report designers
every name (to attach styles) and auditors every customer's metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ForeignKey, LargeBinary, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.crypto.keys import generate_key, load_master_key, unwrap_key, wrap_key
from app.crypto.sealing import seal, unseal
from app.db import Base, UTCDateTime
from app.roles import Capability, Role, can
from app.settings import settings

Visibility = Literal["full", "metadata", "names"]

# The spec's "See customers" row. Assigned means full sight of the customers the
# person is assigned to, and nothing of the others.
SEES_CUSTOMERS: dict[Role, Literal["all", "assigned", "metadata", "names"]] = {
    Role.ADMINISTRATOR: "all",
    Role.TECHNICIAN: "assigned",
    Role.REVIEWER: "assigned",
    Role.AUDITOR: "metadata",
    Role.REPORT_DESIGNER: "names",
}

LANGUAGES = ("da", "en")


class Customer(Base):
    __tablename__ = "customers"
    # IDs appear in the audit log and in what keys are bound to: never reused.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    cvr: Mapped[str | None] = mapped_column(String(8))
    # The customer's own key, wrapped by the master key.
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    # {"address": ...}, sealed with the customer's key.
    sealed: Mapped[bytes] = mapped_column(LargeBinary)
    language: Mapped[str] = mapped_column(String(5))
    # How long raw data is kept after a project is archived.
    retention_months: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class CustomerSite(Base):
    __tablename__ = "customer_sites"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    # {"address": ...}
    sealed: Mapped[bytes] = mapped_column(LargeBinary)


class CustomerContact(Base):
    __tablename__ = "customer_contacts"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    # {"name", "role", "email", "phone"}: all of it is personal data.
    sealed: Mapped[bytes] = mapped_column(LargeBinary)


class CustomerAssignment(Base):
    __tablename__ = "customer_assignments"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# Keys and sealing


def _key_context(customer_id: int) -> bytes:
    return f"skjald/customer-key/{customer_id}".encode()


def bound_to(customer_id: int, kind: str, record_id: int) -> bytes:
    return f"skjald/customer/{customer_id}/{kind}/{record_id}".encode()


def customer_key(customer: Customer) -> bytes:
    master = load_master_key(settings.master_key_path)
    return unwrap_key(master, customer.wrapped_key, context=_key_context(customer.id))


def give_new_key(customer: Customer) -> bytes:
    """Make the customer's key (it needs its ID: flush first). Returns the key."""
    key = generate_key()
    master = load_master_key(settings.master_key_path)
    customer.wrapped_key = wrap_key(master, key, context=_key_context(customer.id))
    return key


class Sealer:
    """Seals and opens one customer's records with its key, unwrapped once."""

    def __init__(self, customer: Customer) -> None:
        self.customer_id = customer.id
        self._key = customer_key(customer)

    def seal(self, kind: str, record_id: int, value: dict[str, Any]) -> bytes:
        return seal(self._key, value, bound_to=bound_to(self.customer_id, kind, record_id))

    def open(self, kind: str, record_id: int, sealed: bytes) -> dict[str, Any]:
        return unseal(self._key, sealed, bound_to=bound_to(self.customer_id, kind, record_id))


# Who sees what


def is_assigned(db: Session, user_id: int, customer_id: int) -> bool:
    return db.get(CustomerAssignment, (customer_id, user_id)) is not None


def assigned_customer_ids(db: Session, user_id: int) -> set[int]:
    return set(db.scalars(
        select(CustomerAssignment.customer_id).where(CustomerAssignment.user_id == user_id)
    ))


def sights(roles: set[Role]) -> set[str]:
    return {SEES_CUSTOMERS[role] for role in roles}


def level_for(sight: set[str], assigned: bool) -> Visibility | None:
    """How much of a customer someone with these sights sees."""
    if "all" in sight or ("assigned" in sight and assigned):
        return "full"
    if "metadata" in sight:
        return "metadata"
    if "names" in sight:
        return "names"
    return None


def visibility(db: Session, user_id: int, roles: set[Role], customer_id: int) -> Visibility | None:
    """How much of one customer this person may see, if anything."""
    return level_for(sights(roles), is_assigned(db, user_id, customer_id))


def may_manage(roles: set[Role]) -> bool:
    return can(roles, Capability.MANAGE_CUSTOMERS)


def may_create_projects(db: Session, user_id: int, roles: set[Role], customer_id: int) -> bool:
    """Create and change projects: Administrators anywhere, technicians for their customers."""
    return can(roles, Capability.CREATE_PROJECTS_AND_REPORTS) and (
        may_manage(roles) or is_assigned(db, user_id, customer_id)
    )
