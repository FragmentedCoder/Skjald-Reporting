"""Deciding whether a username and password may sign in.

Every failure looks the same from outside: same answer, and about the same
time, whether the user exists, the password is wrong or the account is locked.
The reason is kept for the audit log only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.audit import AuditEntry, timestamp
from app.auth.passwords import burn_verify_time, hash_password, needs_rehash, verify_password
from app.policy import SecurityPolicy
from app.users import User, find_user

FAILED_ACTION = "auth.sign_in.failed"
ADDRESS_WINDOW = timedelta(minutes=15)
ADDRESS_MAX_FAILURES = 30


@dataclass(frozen=True)
class SignInOutcome:
    ok: bool
    account: User | None
    reason: str | None = None
    locked_now: bool = False


def authenticate(
    db: Session, username: str, password: str, policy: SecurityPolicy
) -> SignInOutcome:
    """Check a username and password, and update the account's failure count.

    Commits the caller's transaction before checking the password: Argon2 takes
    about 0.1 s, and an open transaction holds the database's write lock (see
    app/db.py), which would stall every other request meanwhile.
    """
    user = find_user(db, username)
    db.commit()

    if user is None:
        burn_verify_time(password)
        return SignInOutcome(False, None, "unknown_user")
    if user.password_hash is None:
        burn_verify_time(password)
        return SignInOutcome(False, user, "no_local_password")
    if user.locked_until is not None and user.locked_until > clock.utcnow():
        burn_verify_time(password)
        return SignInOutcome(False, user, "locked")

    if not verify_password(user.password_hash, password):
        return _record_failure(db, user, policy)
    if not user.is_active:
        return SignInOutcome(False, user, "inactive")

    # The failure count is not reset here but once both factors pass
    # (mfa.upgrade_session), so wrong codes and wrong passwords share one lockout.
    if needs_rehash(user.password_hash):
        new_hash = hash_password(password)
        db.refresh(user)
        user.password_hash = new_hash
    return SignInOutcome(True, user)


def _record_failure(db: Session, user: User, policy: SecurityPolicy) -> SignInOutcome:
    # Re-read under the write lock, so attempts running side by side all count.
    db.refresh(user)
    now: datetime = clock.utcnow()
    user.failed_sign_ins += 1
    if user.failed_sign_ins >= policy.lockout_threshold:
        user.locked_until = now + timedelta(minutes=policy.lockout_minutes)
        user.failed_sign_ins = 0
        return SignInOutcome(False, user, "wrong_password", locked_now=True)
    return SignInOutcome(False, user, "wrong_password")


def too_many_failures_from(db: Session, ip: str | None) -> bool:
    """Throttle by address too, so one machine can't try many usernames below each lockout."""
    since = timestamp(clock.utcnow() - ADDRESS_WINDOW)
    failures = db.scalar(
        select(func.count())
        .select_from(AuditEntry)
        .where(
            AuditEntry.action == FAILED_ACTION,
            AuditEntry.ip == ip,
            AuditEntry.occurred_at >= since,
        )
    )
    return (failures or 0) >= ADDRESS_MAX_FAILURES
