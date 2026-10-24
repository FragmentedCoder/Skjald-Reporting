"""Customers (sites, contacts, assignments, own keys) and projects

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # AUTOINCREMENT: these IDs reach the audit log and what keys are bound to.
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("cvr", sa.String(length=8), nullable=True),
        sa.Column("wrapped_key", sa.LargeBinary(), nullable=False),
        sa.Column("sealed", sa.LargeBinary(), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False),
        sa.Column("retention_months", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_customers_name", "customers", ["name"])
    op.create_table(
        "customer_sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("sealed", sa.LargeBinary(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_customer_sites_customer_id", "customer_sites", ["customer_id"])
    op.create_table(
        "customer_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sealed", sa.LargeBinary(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_customer_contacts_customer_id", "customer_contacts", ["customer_id"])
    op.create_table(
        "customer_assignments",
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_index("ix_customer_assignments_user_id", "customer_assignments", ["user_id"])
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("responsible_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", sa.Integer(),
                  sa.ForeignKey("customer_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("archived_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_projects_customer_id", "projects", ["customer_id"])
    op.create_table(
        "project_sites",
        sa.Column("project_id", sa.Integer(),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("site_id", sa.Integer(),
                  sa.ForeignKey("customer_sites.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_project_sites_site_id", "project_sites", ["site_id"])


def downgrade() -> None:
    for table in ("project_sites", "projects", "customer_assignments", "customer_contacts",
                  "customer_sites", "customers"):
        op.drop_table(table)
