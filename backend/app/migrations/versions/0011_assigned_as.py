"""What people are assigned as: technician or reviewer, per customer and project

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Plain ADD COLUMNs keep every row.
    op.execute("ALTER TABLE customer_assignments ADD COLUMN as_technician BOOLEAN NOT NULL "
               "DEFAULT 0")
    op.execute("ALTER TABLE customer_assignments ADD COLUMN as_reviewer BOOLEAN NOT NULL "
               "DEFAULT 0")
    # Someone assigned so far is assigned as whatever their roles let them be.
    op.execute("""
        UPDATE customer_assignments SET
          as_technician = EXISTS (SELECT 1 FROM user_roles r
            WHERE r.user_id = customer_assignments.user_id AND r.role = 'technician'),
          as_reviewer = EXISTS (SELECT 1 FROM user_roles r
            WHERE r.user_id = customer_assignments.user_id AND r.role = 'reviewer')
    """)
    op.execute("ALTER TABLE project_members ADD COLUMN as_role VARCHAR(20) NOT NULL "
               "DEFAULT 'technician'")
    # A team member is there as a technician if they're one on the customer, else as
    # a reviewer.
    op.execute("""
        UPDATE project_members SET as_role = 'reviewer' WHERE NOT EXISTS (
          SELECT 1 FROM customer_assignments a JOIN projects p ON p.customer_id = a.customer_id
          WHERE p.id = project_members.project_id AND a.user_id = project_members.user_id
            AND a.as_technician)
    """)


def downgrade() -> None:
    op.drop_column("project_members", "as_role")
    op.drop_column("customer_assignments", "as_reviewer")
    op.drop_column("customer_assignments", "as_technician")
