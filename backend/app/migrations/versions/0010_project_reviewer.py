"""A reviewer for each project

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # A plain ADD COLUMN keeps every row; written out so the foreign key is certain.
    op.execute(
        "ALTER TABLE projects ADD COLUMN reviewer_id INTEGER "
        "REFERENCES users (id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.drop_column("projects", "reviewer_id")
