"""Report styles, their versions kept as they were, and customers' style choices

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "styles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(length=100)),
        sa.Column("sealed_name", sa.LargeBinary()),
        sa.Column("based_on", sa.Integer(), sa.ForeignKey("styles.id", ondelete="SET NULL")),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("current", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("removed_at", sa.DateTime()),
        sa.Column("removed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_styles_customer_id", "styles", ["customer_id"])
    op.create_table(
        "style_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("style_id", sa.Integer(), sa.ForeignKey("styles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("sealed_content", sa.LargeBinary()),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.Column("saved_by", sa.Integer()),
        sa.UniqueConstraint("style_id", "number"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_style_versions_style_id", "style_versions", ["style_id"])
    # Every save is kept: a version never changes, and goes only with its style (when
    # its customer is deleted). Foreign key actions run once the style's row is gone.
    op.execute(
        "CREATE TRIGGER style_versions_kept_unchanged BEFORE UPDATE ON style_versions "
        "BEGIN SELECT RAISE(ABORT, 'style versions are kept as they were'); END"
    )
    op.execute(
        "CREATE TRIGGER style_versions_kept BEFORE DELETE ON style_versions "
        "WHEN EXISTS (SELECT 1 FROM styles WHERE id = OLD.style_id) "
        "BEGIN SELECT RAISE(ABORT, 'style versions are kept as they were'); END"
    )
    op.create_table(
        "style_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("style_id", sa.Integer(), sa.ForeignKey("styles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=30), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("style_id", "sha256"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_style_assets_style_id", "style_assets", ["style_id"])
    op.execute(
        "CREATE TRIGGER style_assets_frozen BEFORE UPDATE ON style_assets "
        "BEGIN SELECT RAISE(ABORT, 'style pictures never change'); END"
    )
    op.create_table(
        "style_uploads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("style_id", sa.Integer(), sa.ForeignKey("styles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("original", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("pages", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_style_uploads_style_id", "style_uploads", ["style_id"])
    op.create_table(
        "customer_styles",
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("default_style_id", sa.Integer(),
                  sa.ForeignKey("styles.id", ondelete="SET NULL")),
        sa.Column("allowed", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("customer_styles")
    op.drop_table("style_uploads")
    op.drop_table("style_assets")
    op.drop_table("style_versions")
    op.drop_table("styles")
