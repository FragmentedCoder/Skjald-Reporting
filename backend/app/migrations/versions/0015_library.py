"""The shared library: entries, and every version of each, kept as they were

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "library_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("current", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("locked_at", sa.DateTime()),
        sa.Column("locked_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("removed_at", sa.DateTime()),
        sa.Column("removed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("kind", "key"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "library_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.Integer(),
                  sa.ForeignKey("library_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.Column("saved_by", sa.Integer()),
        sa.UniqueConstraint("entry_id", "number"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_library_versions_entry_id", "library_versions", ["entry_id"])
    # Every change is kept: a version is never changed or removed.
    op.execute(
        "CREATE TRIGGER library_versions_kept_unchanged BEFORE UPDATE ON library_versions "
        "BEGIN SELECT RAISE(ABORT, 'library versions are kept as they were'); END"
    )
    op.execute(
        "CREATE TRIGGER library_versions_kept BEFORE DELETE ON library_versions "
        "BEGIN SELECT RAISE(ABORT, 'library versions are kept as they were'); END"
    )


def downgrade() -> None:
    op.drop_table("library_versions")
    op.drop_table("library_entries")
