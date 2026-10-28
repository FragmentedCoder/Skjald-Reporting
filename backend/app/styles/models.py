"""Report styles, as stored: styles, every version of each, their pictures, and the
style each customer's reports use.

A company style stacks on the Skjald default; a customer style on one company style
(or on the Skjald default). Each save adds a version, which the database refuses to
change, and refuses to delete while its style exists (migration 0017), so the history
stays whole; removing a style marks it removed. A customer style's name, versions and
pictures are sealed with the customer's key, and deleting the customer deletes them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime


class Style(Base):
    __tablename__ = "styles"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    # None: a company style.
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    # A company style's name; a customer style's is sealed with the customer's key.
    name: Mapped[str | None] = mapped_column(String(100))
    sealed_name: Mapped[bytes | None] = mapped_column(LargeBinary)
    # The company style a customer style stacks on; None: the Skjald default.
    based_on: Mapped[int | None] = mapped_column(ForeignKey("styles.id", ondelete="SET NULL"))
    # The company style reports use unless a customer's choice says otherwise.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    current: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    removed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class StyleVersion(Base):
    __tablename__ = "style_versions"
    __table_args__ = (UniqueConstraint("style_id", "number"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    style_id: Mapped[int] = mapped_column(ForeignKey("styles.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    # The StyleContent as JSON: plain for a company style, sealed for a customer's.
    content: Mapped[str | None] = mapped_column(Text)
    sealed_content: Mapped[bytes | None] = mapped_column(LargeBinary)
    saved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # A plain user ID, as in the audit log: a version never changes.
    saved_by: Mapped[int | None] = mapped_column(Integer)


class StyleAsset(Base):
    """A picture a style uses: an image element's or artwork, kept by its SHA-256."""

    __tablename__ = "style_assets"
    __table_args__ = (UniqueConstraint("style_id", "sha256"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    style_id: Mapped[int] = mapped_column(ForeignKey("styles.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(30))
    # The picture: plain for a company style; {"data": base64} sealed for a customer's.
    data: Mapped[bytes] = mapped_column(LargeBinary)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class StyleUpload(Base):
    """A PDF on its way to becoming artwork, converted by the renderer."""

    __tablename__ = "style_uploads"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    style_id: Mapped[int] = mapped_column(ForeignKey("styles.id", ondelete="CASCADE"), index=True)
    # The PDF (sealed for a customer style), emptied once converted.
    original: Mapped[bytes] = mapped_column(LargeBinary)
    # converting, ready or failed
    status: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(String(300), default="")
    # The pages' SHA-256s, as a JSON list, once converted.
    pages: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class CustomerStyles(Base):
    """The styles a customer's reports may use, and the one they start with."""

    __tablename__ = "customer_styles"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    # None: the company's default style.
    default_style_id: Mapped[int | None] = mapped_column(
        ForeignKey("styles.id", ondelete="SET NULL"))
    # Others a technician may pick, as a JSON list of style IDs.
    allowed: Mapped[str] = mapped_column(Text, default="[]")
