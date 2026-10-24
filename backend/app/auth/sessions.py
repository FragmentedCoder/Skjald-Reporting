"""Server-side sessions. The browser holds a random token; the database holds only its hash."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app import clock
from app.db import Base, UTCDateTime
from app.policy import SecurityPolicy
from app.users import User

# __Host- makes browsers refuse the cookie unless it is Secure, has Path=/ and no Domain.
COOKIE_NAME = "__Host-skjald_session"

# Recording activity on every request would mean a write per request.
TOUCH_INTERVAL = timedelta(minutes=1)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(lazy="joined")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token_for(token: str) -> str:
    """Derived from the session token, so it needs no storage and dies with the session."""
    return hmac.new(token.encode(), b"skjald/csrf", hashlib.sha256).hexdigest()


def start_session(
    db: Session,
    user: User,
    policy: SecurityPolicy,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(32)
    now = clock.utcnow()
    record = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        user=user,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=policy.max_session_hours),
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(record)
    db.flush()
    return token, record


def find_live_session(db: Session, token: str, policy: SecurityPolicy) -> UserSession | None:
    """The session for token if it is still valid; an expired one is deleted on the way."""
    record = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if record is None:
        return None
    now = clock.utcnow()
    idle_limit = record.last_seen_at + timedelta(minutes=policy.idle_timeout_minutes)
    if now >= record.expires_at or now >= idle_limit or not record.user.is_active:
        db.delete(record)
        return None
    if now - record.last_seen_at >= TOUCH_INTERVAL:
        record.last_seen_at = now
    return record
