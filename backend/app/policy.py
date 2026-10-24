"""Security settings Administrators can change (see docs/architecture.md, "Login")."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base

POLICY_KEY = "security_policy"


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


@dataclass(frozen=True)
class SecurityPolicy:
    min_password_length: int = 12
    lockout_threshold: int = 10
    lockout_minutes: int = 15
    idle_timeout_minutes: int = 30
    max_session_hours: int = 12


def load_policy(db: Session) -> SecurityPolicy:
    stored = db.get(Setting, POLICY_KEY)
    if stored is None:
        return SecurityPolicy()
    known = {field.name for field in fields(SecurityPolicy)}
    return SecurityPolicy(**{k: v for k, v in json.loads(stored.value).items() if k in known})


def save_policy(db: Session, policy: SecurityPolicy) -> None:
    db.merge(Setting(key=POLICY_KEY, value=json.dumps(asdict(policy))))
