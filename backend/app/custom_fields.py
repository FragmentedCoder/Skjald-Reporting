"""Custom fields: details the company keeps about customers and projects beyond the
built-in ones, such as a customer's support agreement or a project's ticket number.

Administrators and Report Designers define them (BUILD_TEMPLATES: the spec gives
custom fields to the people who build templates); Managers and Administrators fill
them in on the customer and project forms. The definitions hold no customer data and
are plain; the values go into the customer's or project's sealed details, under
"custom", so they're sealed with the customer's key like the rest. Templates read
them as customer.custom.<key> and project.custom.<key>. A field's key and type never
change once made, since templates read them; a field no longer wanted is archived,
which keeps the values already filled in.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import audit, clock
from app.auth.dependencies import DB, FullSession, client_ip, require
from app.auth.sessions import UserSession
from app.db import Base, UTCDateTime
from app.roles import Capability
from app.templates.fields import KEY_PATTERN

AppliesTo = Literal["customer", "project"]
FieldType = Literal["text", "long_text", "number", "date", "yes_no", "dropdown", "email", "phone"]

# The type each field gives templates' expressions.
CEL_TYPES: dict[str, str] = {
    "text": "string", "long_text": "string", "number": "double", "date": "timestamp",
    "yes_no": "bool", "dropdown": "string", "email": "string", "phone": "string",
}
MAX_FIELDS = 100
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9 ()./-]{3,30}$")


class CustomField(Base):
    __tablename__ = "custom_fields"
    __table_args__ = (UniqueConstraint("applies_to", "key"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    applies_to: Mapped[str] = mapped_column(String(10))
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    help: Mapped[str] = mapped_column(String(300), default="")
    # A dropdown's choices, as a JSON list.
    options: Mapped[str] = mapped_column(Text, default="[]")
    position: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


def fields_for(db: Session, applies_to: str, *, archived: bool = False) -> list[CustomField]:
    query = select(CustomField).where(CustomField.applies_to == applies_to)
    if not archived:
        query = query.where(CustomField.archived.is_(False))
    return list(db.scalars(query.order_by(CustomField.position, CustomField.id)))


def custom_names(db: Session) -> dict[str, str]:
    """The names templates read custom fields by, with their types."""
    return {f"{f.applies_to}.custom.{f.key}": CEL_TYPES[f.type]
            for f in db.scalars(select(CustomField).where(CustomField.archived.is_(False)))}


def _value(field: CustomField, raw: Any) -> Any:
    """One value, checked and tidied for its field; ValueError says what's wrong."""
    label = field.label
    if field.type in ("text", "long_text", "email", "phone", "dropdown", "date"):
        if not isinstance(raw, str):
            raise ValueError(f"{label} takes text.")
        text = raw.strip()
        if field.type == "text" and len(text) > 500:
            raise ValueError(f"{label} takes at most 500 characters.")
        if field.type == "long_text" and len(text) > 5000:
            raise ValueError(f"{label} takes at most 5,000 characters.")
        if field.type == "email" and not _EMAIL.match(text):
            raise ValueError(f"{label} needs an email address, such as it@example.com.")
        if field.type == "phone" and not _PHONE.match(text):
            raise ValueError(f"{label} needs a phone number, such as +45 70 20 30 40.")
        if field.type == "dropdown" and text not in json.loads(field.options):
            raise ValueError(f"Choose one of {label}'s options.")
        if field.type == "date":
            try:
                date.fromisoformat(text)
            except ValueError:
                raise ValueError(f"{label} needs a date.") from None
        return text
    if field.type == "number":
        if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
            raise ValueError(f"{label} takes a number.")
        return float(raw)
    if not isinstance(raw, bool):
        raise ValueError(f"{label} is yes or no.")
    return raw


def merge_values(db: Session, applies_to: str, stored: dict[str, Any] | None,
                 given: dict[str, Any]) -> dict[str, Any]:
    """The values after a change: each given one checked for its field, an empty one
    (None or "") cleared. Values of archived fields are kept but can't be changed.
    Raises HTTPException 400 with a message fit to show."""
    fields = {f.key: f for f in fields_for(db, applies_to)}
    values = dict(stored or {})
    for key, raw in given.items():
        field = fields.get(key)
        if field is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"There's no custom field “{key}”.")
        if raw is None or raw == "":
            values.pop(key, None)
            continue
        try:
            values[key] = _value(field, raw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return values


def shown_values(db: Session, applies_to: str, stored: dict[str, Any] | None) -> dict[str, Any]:
    """The values of the fields still in use, for forms and templates."""
    keys = {f.key for f in fields_for(db, applies_to)}
    return {k: v for k, v in (stored or {}).items() if k in keys}


# The API

router = APIRouter(prefix="/custom-fields")
Definer = Annotated[UserSession, Depends(require(Capability.BUILD_TEMPLATES))]
NOT_FOUND = "That custom field doesn't exist."


class FieldIn(BaseModel):
    applies_to: AppliesTo
    key: str = Field(pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=100)
    type: FieldType
    help: str = Field(default="", max_length=300)
    options: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=100)

    @field_validator("label", "help")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _options(self) -> FieldIn:
        self.options = [o.strip() for o in self.options]
        if self.type == "dropdown" and not self.options:
            raise ValueError("A dropdown needs at least one option.")
        if self.type != "dropdown":
            self.options = []
        if len(set(self.options)) != len(self.options):
            raise ValueError("Each option can be listed once.")
        return self


class FieldUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    help: str = Field(default="", max_length=300)
    options: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=100)
    position: int = Field(default=0, ge=0, le=10_000)
    archived: bool = False


class FieldOut(BaseModel):
    id: int
    applies_to: AppliesTo
    key: str
    label: str
    type: FieldType
    help: str
    options: list[str]
    position: int
    archived: bool


def _out(field: CustomField) -> FieldOut:
    return FieldOut(id=field.id, applies_to=field.applies_to,  # type: ignore[arg-type]
                    key=field.key, label=field.label, type=field.type,  # type: ignore[arg-type]
                    help=field.help, options=json.loads(field.options), position=field.position,
                    archived=field.archived)


def _log(db: Session, request: Request, record: UserSession, action: str, field: CustomField,
         **details: object) -> None:
    audit.append(db, action, actor_id=record.user.id, actor_name=record.user.username,
                 target_type="custom_field", target_id=str(field.id), ip=client_ip(request),
                 details={"applies_to": field.applies_to, "key": field.key, **details})


@router.get("")
def list_fields(record: FullSession, db: DB, archived: bool = False) -> list[FieldOut]:
    """The definitions, which hold no customer data: anyone signed in may read them."""
    return [_out(f) for kind in ("customer", "project")
            for f in fields_for(db, kind, archived=archived)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_field(body: FieldIn, request: Request, record: Definer, db: DB) -> FieldOut:
    taken = db.scalar(select(CustomField).where(CustomField.applies_to == body.applies_to,
                                                CustomField.key == body.key))
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "A field with that name exists, perhaps archived: restore it, "
                            "or choose another name.")
    count = len(fields_for(db, body.applies_to, archived=True))
    if count >= MAX_FIELDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"There can be at most {MAX_FIELDS} fields of each kind.")
    field = CustomField(applies_to=body.applies_to, key=body.key, label=body.label,
                        type=body.type, help=body.help, options=json.dumps(body.options),
                        position=count, archived=False, created_at=clock.utcnow(),
                        created_by=record.user_id)
    db.add(field)
    db.flush()
    _log(db, request, record, "custom_field.created", field, type=body.type)
    db.commit()
    return _out(field)


@router.put("/{field_id}")
def update_field(field_id: int, body: FieldUpdate, request: Request, record: Definer, db: DB
                 ) -> FieldOut:
    """The label, help, options, place and whether it's archived; never its key or type."""
    field = db.get(CustomField, field_id)
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    options = [o.strip() for o in body.options] if field.type == "dropdown" else []
    if field.type == "dropdown" and not options:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A dropdown needs at least one option.")
    if len(set(options)) != len(options):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Each option can be listed once.")
    changed = [name for name, before, after in (
        ("label", field.label, body.label.strip()), ("help", field.help, body.help.strip()),
        ("options", json.loads(field.options), options), ("position", field.position,
                                                           body.position),
        ("archived", field.archived, body.archived)) if before != after]
    field.label, field.help = body.label.strip(), body.help.strip()
    field.options, field.position = json.dumps(options), body.position
    field.archived = body.archived
    if changed:
        field.changed_at = clock.utcnow()
        action = ("custom_field.archived" if changed == ["archived"] and body.archived
                  else "custom_field.restored" if changed == ["archived"]
                  else "custom_field.changed")
        _log(db, request, record, action, field, fields=changed)
    db.commit()
    return _out(field)
