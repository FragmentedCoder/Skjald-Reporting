"""The shared library API: variables, text snippets and data tables.

Report Designers, Technicians and Administrators read and change entries
(EDIT_LIBRARY); Administrators lock and unlock them (LOCK_LIBRARY_ENTRIES), and
nobody changes a locked entry. Every change is a new version, refused if it was
made from an older one than the newest (409), and written to the audit log with
the entry's kind, key and version; the value itself stays in the library.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock
from app.auth.dependencies import DB, client_ip, require
from app.auth.sessions import UserSession
from app.library.models import LibraryEntry, LibraryVersion
from app.library.values import KEY_PATTERN, Kind, parse_value, table_from_csv, table_from_json
from app.roles import Capability
from app.users import User

router = APIRouter(prefix="/library")

Editor = Annotated[UserSession, Depends(require(Capability.EDIT_LIBRARY))]
Locker = Annotated[UserSession, Depends(require(Capability.LOCK_LIBRARY_ENTRIES))]

NOT_FOUND = "That library entry doesn't exist."
MAX_IMPORT_BYTES = 2 * 1024 * 1024


class EntryIn(BaseModel):
    kind: Kind
    key: str = Field(pattern=KEY_PATTERN)
    description: str = Field(default="", max_length=500)
    value: dict[str, Any]


class EntryUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    value: dict[str, Any]
    # The version the change was made from: a change over a newer one is refused.
    version: int


class EntryOut(BaseModel):
    id: int
    kind: Kind
    key: str
    description: str
    value: dict[str, Any]
    version: int
    updated_at: datetime
    updated_by: str | None
    locked: bool
    locked_by: str | None


class VersionOut(BaseModel):
    number: int
    value: dict[str, Any]
    saved_at: datetime
    saved_by: str | None


def _log(db: Session, request: Request, record: UserSession, action: str, entry: LibraryEntry,
         **details: object) -> None:
    audit.append(db, action, actor_id=record.user.id, actor_name=record.user.username,
                 target_type="library_entry", target_id=str(entry.id), ip=client_ip(request),
                 details={"kind": entry.kind, "key": entry.key, **details})


def _value(raw: dict[str, Any], kind: str) -> dict[str, Any]:
    try:
        return parse_value(kind, raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        message = first["msg"].removeprefix("Value error, ")
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message) from None


def _entry(db: Session, entry_id: int) -> LibraryEntry:
    entry = db.get(LibraryEntry, entry_id)
    if entry is None or entry.removed_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return entry


def _version(db: Session, entry: LibraryEntry, number: int | None = None) -> LibraryVersion:
    found = db.scalar(select(LibraryVersion).where(
        LibraryVersion.entry_id == entry.id, LibraryVersion.number == (number or entry.current)))
    assert found is not None
    return found


def _names(db: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(wanted)))
    return {user_id: name for user_id, name in rows}


def _out(entry: LibraryEntry, version: LibraryVersion, names: dict[int, str]) -> EntryOut:
    return EntryOut(
        id=entry.id, kind=cast(Kind, entry.kind), key=entry.key, description=entry.description,
        value=json.loads(version.value), version=version.number, updated_at=version.saved_at,
        updated_by=names.get(version.saved_by or 0), locked=entry.locked_at is not None,
        locked_by=names.get(entry.locked_by or 0),
    )


def _one(db: Session, entry: LibraryEntry) -> EntryOut:
    version = _version(db, entry)
    return _out(entry, version, _names(db, {version.saved_by, entry.locked_by}))


def current_entries(db: Session) -> list[tuple[LibraryEntry, LibraryVersion]]:
    """Every entry in use with its newest version, for templates and reports."""
    rows = db.execute(
        select(LibraryEntry, LibraryVersion)
        .join(LibraryVersion, (LibraryVersion.entry_id == LibraryEntry.id)
              & (LibraryVersion.number == LibraryEntry.current))
        .where(LibraryEntry.removed_at.is_(None))
        .order_by(LibraryEntry.kind, LibraryEntry.key)
    )
    return [(row[0], row[1]) for row in rows]


def _add_version(db: Session, entry: LibraryEntry, value: dict[str, Any], user_id: int) -> None:
    entry.current += 1
    db.add(LibraryVersion(entry_id=entry.id, number=entry.current,
                          value=json.dumps(value, ensure_ascii=False, sort_keys=True),
                          saved_at=clock.utcnow(), saved_by=user_id))


@router.get("")
def list_entries(record: Editor, db: DB) -> list[EntryOut]:
    pairs = current_entries(db)
    names = _names(db, {v.saved_by for _, v in pairs} | {e.locked_by for e, _ in pairs})
    return [_out(entry, version, names) for entry, version in pairs]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_entry(body: EntryIn, request: Request, record: Editor, db: DB) -> EntryOut:
    value = _value(body.value, body.kind)
    existing = db.scalar(select(LibraryEntry).where(LibraryEntry.kind == body.kind,
                                                    LibraryEntry.key == body.key))
    if existing is not None and existing.removed_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The library has {body.key} already.")
    now = clock.utcnow()
    if existing is not None:
        # Taken up again: a new version of the entry that was removed.
        existing.removed_at = existing.removed_by = None
        existing.description = body.description
        _add_version(db, existing, value, record.user_id)
        entry = existing
    else:
        entry = LibraryEntry(kind=body.kind, key=body.key, description=body.description, current=1,
                             created_at=now, created_by=record.user_id)
        db.add(entry)
        db.flush()
        db.add(LibraryVersion(entry_id=entry.id, number=1,
                              value=json.dumps(value, ensure_ascii=False, sort_keys=True),
                              saved_at=now, saved_by=record.user_id))
    _log(db, request, record, "library.created", entry, version=entry.current)
    db.commit()
    return _one(db, entry)


@router.put("/{entry_id}")
def update_entry(entry_id: int, body: EntryUpdate, request: Request, record: Editor, db: DB
                 ) -> EntryOut:
    entry = _entry(db, entry_id)
    if entry.locked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An administrator locked this entry: nobody can change it until "
                            "it's unlocked.")
    if body.version != entry.current:
        who = _names(db, {_version(db, entry).saved_by}).get(_version(db, entry).saved_by or 0)
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{who or 'Someone'} changed this entry since you opened it. "
                            "Reload it to see their change.")
    value = _value(body.value, entry.kind)
    if body.description is not None:
        entry.description = body.description
    if json.loads(_version(db, entry).value) != value:
        _add_version(db, entry, value, record.user_id)
    _log(db, request, record, "library.changed", entry, version=entry.current)
    db.commit()
    return _one(db, entry)


@router.post("/{entry_id}/import")
def import_table(entry_id: int, data: Annotated[bytes, Body(media_type="application/octet-stream")],
                 request: Request, record: Editor, db: DB,
                 format: Annotated[Literal["csv", "json"], Query()] = "csv") -> EntryOut:
    """A data table's rows from a CSV file (first row: the column names; first column:
    the keys) or a JSON one."""
    entry = _entry(db, entry_id)
    if entry.kind != "table":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only data tables are imported.")
    if entry.locked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An administrator locked this entry.")
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 2 MB.")
    try:
        text = data.decode("utf-8")
        value = table_from_json(text) if format == "json" else table_from_csv(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "That file can't be read: use UTF-8 CSV or JSON.") from exc
    except ValidationError as exc:
        message = exc.errors()[0]["msg"].removeprefix("Value error, ")
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    _add_version(db, entry, value, record.user_id)
    _log(db, request, record, "library.imported", entry, version=entry.current,
         rows=len(value["rows"]))
    db.commit()
    return _one(db, entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_entry(entry_id: int, request: Request, record: Editor, db: DB) -> Response:
    entry = _entry(db, entry_id)
    if entry.locked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An administrator locked this entry.")
    entry.removed_at = clock.utcnow()
    entry.removed_by = record.user_id
    _log(db, request, record, "library.removed", entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{entry_id}/versions")
def versions(entry_id: int, record: Editor, db: DB) -> list[VersionOut]:
    entry = _entry(db, entry_id)
    found = list(db.scalars(select(LibraryVersion).where(LibraryVersion.entry_id == entry.id)
                            .order_by(LibraryVersion.number.desc())))
    names = _names(db, {v.saved_by for v in found})
    return [VersionOut(number=v.number, value=json.loads(v.value), saved_at=v.saved_at,
                       saved_by=names.get(v.saved_by or 0)) for v in found]


@router.post("/{entry_id}/lock")
def lock(entry_id: int, request: Request, record: Locker, db: DB) -> EntryOut:
    entry = _entry(db, entry_id)
    if entry.locked_at is None:
        entry.locked_at = clock.utcnow()
        entry.locked_by = record.user_id
        _log(db, request, record, "library.locked", entry)
        db.commit()
    return _one(db, entry)


@router.post("/{entry_id}/unlock")
def unlock(entry_id: int, request: Request, record: Locker, db: DB) -> EntryOut:
    entry = _entry(db, entry_id)
    if entry.locked_at is not None:
        entry.locked_at = entry.locked_by = None
        _log(db, request, record, "library.unlocked", entry)
        db.commit()
    return _one(db, entry)
