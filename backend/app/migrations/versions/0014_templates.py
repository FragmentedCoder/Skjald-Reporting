"""Templates, their versions frozen once published, and their images

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(length=36), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("retired_at", sa.DateTime()),
        sa.Column("retired_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "template_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(),
                  sa.ForeignKey("templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.Column("saved_by", sa.Integer()),
        sa.Column("logged_at", sa.DateTime()),
        sa.Column("logged_by", sa.Integer()),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("published_by", sa.Integer()),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.UniqueConstraint("template_id", "number"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_template_versions_template_id", "template_versions", ["template_id"])
    op.create_index("ix_template_versions_one_draft", "template_versions", ["template_id"],
                    unique=True, sqlite_where=sa.text("number IS NULL"))
    # What reports are pinned to can't change: an application bug can't alter or remove
    # a published version (someone with the database key could drop these, as with the
    # audit log's guard). The draft becomes a version by getting its number.
    op.execute(
        "CREATE TRIGGER template_versions_frozen BEFORE UPDATE ON template_versions "
        "WHEN OLD.number IS NOT NULL "
        "BEGIN SELECT RAISE(ABORT, 'published template versions are frozen'); END"
    )
    op.execute(
        "CREATE TRIGGER template_versions_kept BEFORE DELETE ON template_versions "
        "WHEN OLD.number IS NOT NULL "
        "BEGIN SELECT RAISE(ABORT, 'published template versions are kept'); END"
    )
    op.create_table(
        "template_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(),
                  sa.ForeignKey("templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer()),
        sa.UniqueConstraint("template_id", "sha256"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_template_assets_template_id", "template_assets", ["template_id"])
    op.execute(
        "CREATE TRIGGER template_assets_frozen BEFORE UPDATE ON template_assets "
        "BEGIN SELECT RAISE(ABORT, 'template images never change'); END"
    )


def downgrade() -> None:
    op.drop_table("template_assets")
    op.drop_table("template_versions")
    op.drop_table("templates")
