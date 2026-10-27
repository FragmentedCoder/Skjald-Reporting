"""The shared library, as stored: entries and every version of each.

An entry is a variable (vars.<key>), a text snippet (text.<key>) or a data table
(read with lookup("<key>", key)). Each change adds a version, which the database
refuses to change or delete (migration 0015), so the history stays whole;
removing an entry marks it removed and keeps its versions. The library holds no
customer data, so nothing here is sealed with a customer's key.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    __table_args__ = (UniqueConstraint("kind", "key"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    # variable, snippet or table
    kind: Mapped[str] = mapped_column(String(10))
    key: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500), default="")
    current: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Locked by an Administrator: nobody changes it until it's unlocked.
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    locked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    removed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class LibraryVersion(Base):
    __tablename__ = "library_versions"
    __table_args__ = (UniqueConstraint("entry_id", "number"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("library_entries.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    # The value as JSON: {"value": ...}, {"text": ...} or {"columns": [...], "rows": {...}}.
    value: Mapped[str] = mapped_column(Text)
    saved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # A plain user ID, as in the audit log: a version never changes.
    saved_by: Mapped[int | None] = mapped_column(Integer)
