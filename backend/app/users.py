from __future__ import annotations

import unicodedata
from datetime import datetime

from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import clock
from app.auth.passwords import check_password, hash_password
from app.db import Base, UTCDateTime
from app.policy import SecurityPolicy


class User(Base):
    __tablename__ = "users"

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


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().casefold()


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == normalize_username(username)))


def create_user(
    db: Session,
    username: str,
    display_name: str,
    password: str,
    *,
    policy: SecurityPolicy,
    email: str | None = None,
) -> User:
    """Raises PasswordRejected if the password breaks the policy. Callers write the audit entry."""
    username = normalize_username(username)
    check_password(password, policy, username=username)
    now = clock.utcnow()
    user = User(
        username=username,
        display_name=display_name.strip(),
        email=email,
        password_hash=hash_password(password),
        is_active=True,
        failed_sign_ins=0,
        password_changed_at=now,
        created_at=now,
    )
    db.add(user)
    db.flush()
    return user
