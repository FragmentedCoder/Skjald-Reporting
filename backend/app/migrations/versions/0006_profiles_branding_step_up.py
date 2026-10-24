"""Business profile fields, pictures and logo, step-up, ended sessions, audit actor index

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None

PROFILE_COLUMNS = (
    ("first_name", 100),
    ("middle_name", 100),
    ("last_name", 100),
    ("job_title", 150),
    ("department", 150),
    ("phone", 50),
)


def upgrade() -> None:
    # Plain ADD COLUMN, never a table rebuild (see 0003).
    for name, length in PROFILE_COLUMNS:
        op.add_column("users", sa.Column(name, sa.String(length=length), nullable=True))
    op.add_column("user_sessions", sa.Column("confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("user_sessions", sa.Column("ended_reason", sa.String(length=20), nullable=True))
    op.create_table(
        "stored_images",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # The audit log filters by who did it; without this, every such page scans it all.
    op.create_index("ix_audit_log_actor_name", "audit_log", ["actor_name"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_actor_name", table_name="audit_log")
    op.drop_table("stored_images")
    op.drop_column("user_sessions", "ended_reason")
    op.drop_column("user_sessions", "confirmed_at")
    for name, _ in reversed(PROFILE_COLUMNS):
        op.drop_column("users", name)
