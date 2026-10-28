"""Templates and their versions, as stored.

A template has at most one draft and any number of published versions. Publishing
freezes the draft as the next version number; the database itself refuses any
change to a published version, or its deletion (the triggers in migration 0014),
so an application bug can't alter what reports are pinned to. A template that was
never published can be deleted; one that was is retired instead.

Images uploaded with a template are kept by their SHA-256, never changed, and
shared by all its versions; blocks name them by that hash, so a .skjald file can
carry them as they are.

Templates hold no customer data, so nothing here is sealed with a customer's key;
the database's own encryption covers it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime


class Template(Base):
    __tablename__ = "templates"
    # IDs appear in the audit log: never reused.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    # Names the template across installs, so an imported copy can be recognised.
    uuid: Mapped[str] = mapped_column(String(36), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # No new reports from a retired template; reports made with it are unchanged.
    retired_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    retired_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "number"),
        # One draft per template: the row whose number isn't set yet.
        Index("ix_template_versions_one_draft", "template_id", unique=True,
              sqlite_where=text("number IS NULL")),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True)
    # 1, 2, 3 once published; the draft has none.
    number: Mapped[int | None] = mapped_column(Integer)
    # The JSON document app/templates/content.py describes.
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer)
    # Counts the draft's saves, so a save over someone else's newer one is refused.
    revision: Mapped[int] = mapped_column(Integer, default=1)
    # Who saved and published it, by user ID: plain numbers, as in the audit log, since
    # a published row can't change for a foreign key to clear it.
    saved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    saved_by: Mapped[int | None] = mapped_column(Integer)
    # The last time a save was written to the audit log, and by whom: saves while
    # someone works are logged once every few minutes, not every one.
    logged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    logged_by: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    published_by: Mapped[int | None] = mapped_column(Integer)
    # What changed, written by whoever published it.
    note: Mapped[str] = mapped_column(String(500), default="")


class TemplateAsset(Base):
    __tablename__ = "template_assets"
    __table_args__ = (UniqueConstraint("template_id", "sha256"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True)
    # Of the stored file (re-encoded, or sanitised), which blocks name it by.
    sha256: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(50))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(Integer)
