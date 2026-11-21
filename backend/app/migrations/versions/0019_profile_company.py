"""A person's own company in their profile

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Plain ADD COLUMN, never a table rebuild (see 0003).
    op.add_column("users", sa.Column("company", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "company")
