"""Daily RFC 3161 timestamps of the audit log's newest entry

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "audit_stamps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("tsa_url", sa.String(length=300), nullable=False),
        sa.Column("token", sa.LargeBinary(), nullable=False),
        sa.Column("stamped_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_audit_stamps_seq", "audit_stamps", ["seq"])


def downgrade() -> None:
    op.drop_index("ix_audit_stamps_seq", table_name="audit_stamps")
    op.drop_table("audit_stamps")
