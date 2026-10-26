"""Colour choices per person, and step-up confirmations per session

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Plain ADD COLUMN, never a table rebuild (see 0003).
    op.add_column("users", sa.Column("primary_colour", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("accent_colour", sa.String(length=20), nullable=True))
    op.add_column("user_sessions", sa.Column("step_up_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_sessions", "step_up_at")
    op.drop_column("users", "accent_colour")
    op.drop_column("users", "primary_colour")
