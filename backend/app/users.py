from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import LargeBinary, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import clock
from app.auth import pwned
from app.auth.passwords import (
    PasswordRejected,
    check_password,
    hash_password,
    normalize_password,
)
from app.db import Base, UTCDateTime
from app.policy import SecurityPolicy


class User(Base):
    __tablename__ = "users"
    # IDs appear in the audit log, so one must never be reused for someone else.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    # None for accounts that sign in through a directory (release 1.2), never locally.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_sign_ins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Random, not the user id: passkeys store it, and it shouldn't identify anyone.
    webauthn_handle: Mapped[bytes | None] = mapped_column(LargeBinary, unique=True, index=True)


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().casefold()


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == normalize_username(username)))


@dataclass(frozen=True)
class NewPassword:
    """A password that passed every rule, the breach check included.

    Only vet_new_password makes these, and create_user takes nothing else, so a
    code path can't set a password without the checks.
    """

    value: str = field(repr=False)
    username: str


def vet_new_password(password: str, policy: SecurityPolicy, *, username: str) -> NewPassword:
    """Check a new password against every rule.

    Makes a network call when the breach check is on, so call it outside any
    database transaction. Raises PasswordRejected, or pwned.BreachCheckUnavailable
    when the breach check can't be reached.
    """
    username = normalize_username(username)
    check_password(password, policy, username=username)
    if policy.breach_check_enabled and pwned.times_breached(normalize_password(password)):
        raise PasswordRejected(
            "This password has appeared in a data breach, so attackers try it early. "
            "Choose another."
        )
    return NewPassword(password, username)


def create_user(
    db: Session,
    username: str,
    display_name: str,
    password: NewPassword,
    *,
    email: str | None = None,
) -> User:
    """Callers write the audit entry."""
    username = normalize_username(username)
    if password.username != username:
        raise ValueError("The password was vetted for a different username.")
    now = clock.utcnow()
    user = User(
        username=username,
        display_name=display_name.strip(),
        email=email,
        password_hash=hash_password(password.value),
        is_active=True,
        failed_sign_ins=0,
        password_changed_at=now,
        created_at=now,
    )
    db.add(user)
    db.flush()
    return user
