"""Customers' report backgrounds, sealed with each customer's key

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "customer_backgrounds",
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sealed_original", sa.LargeBinary(), nullable=False),
        sa.Column("sealed_pages", sa.LargeBinary()),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("margin_top", sa.Float(), nullable=False),
        sa.Column("margin_bottom", sa.Float(), nullable=False),
        sa.Column("margin_left", sa.Float(), nullable=False),
        sa.Column("margin_right", sa.Float(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )


def downgrade() -> None:
    op.drop_table("customer_backgrounds")
