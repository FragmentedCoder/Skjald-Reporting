"""Jobs for the background worker

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # AUTOINCREMENT: job IDs reach the audit log.
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("requested_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("slot", sa.String(length=80), nullable=True, unique=True),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_jobs_kind", "jobs", ["kind"])
    op.create_index("ix_jobs_state_run_after", "jobs", ["state", "run_after"])


def downgrade() -> None:
    op.drop_index("ix_jobs_state_run_after", table_name="jobs")
    op.drop_index("ix_jobs_kind", table_name="jobs")
    op.drop_table("jobs")
