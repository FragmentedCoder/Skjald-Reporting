"""Reports and their checkouts

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(length=30), nullable=False),
        # No ON DELETE: a template version a report is pinned to can't be deleted.
        sa.Column("template_version_id", sa.Integer(),
                  sa.ForeignKey("template_versions.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("sealed_title", sa.LargeBinary(), nullable=False),
        sa.Column("sealed_answers", sa.LargeBinary(), nullable=False),
        sa.Column("site_id", sa.Integer(),
                  sa.ForeignKey("customer_sites.id", ondelete="SET NULL")),
        sa.Column("saves", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("logged_at", sa.DateTime()),
        sa.Column("logged_by", sa.Integer()),
        sa.UniqueConstraint("number"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_reports_project_id", "reports", ["project_id"])
    op.create_index("ix_reports_template_version_id", "reports", ["template_version_id"])
    op.create_table(
        "report_checkouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(),
                  sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.String(length=40)),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("taken_at", sa.DateTime(), nullable=False),
        sa.Column("active_at", sa.DateTime(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_report_checkouts_report_id", "report_checkouts", ["report_id"])
    op.create_index("ix_report_checkouts_user_id", "report_checkouts", ["user_id"])
    # A step is held once, and so is the whole report (no step).
    op.create_index("ix_report_checkouts_step", "report_checkouts", ["report_id", "step_id"],
                    unique=True, sqlite_where=sa.text("step_id IS NOT NULL"))
    op.create_index("ix_report_checkouts_whole", "report_checkouts", ["report_id"],
                    unique=True, sqlite_where=sa.text("step_id IS NULL"))


def downgrade() -> None:
    op.drop_table("report_checkouts")
    op.drop_table("reports")
