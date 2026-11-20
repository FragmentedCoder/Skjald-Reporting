"""Published template versions may go with their template once it's retired

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | None = None
depends_on: str | None = None

KEPT = (
    "CREATE TRIGGER template_versions_kept BEFORE DELETE ON template_versions "
    "WHEN OLD.number IS NOT NULL{also} "
    "BEGIN SELECT RAISE(ABORT, 'published template versions are kept'); END"
)


def upgrade() -> None:
    # Administrators and Managers may delete a retired template, versions and all. The
    # guard still refuses removing a published version of a template in use; the app
    # deletes a retired template's versions first, while the guard can see it's retired.
    op.execute("DROP TRIGGER template_versions_kept")
    op.execute(KEPT.format(also=" AND (SELECT retired_at FROM templates "
                                "WHERE id = OLD.template_id) IS NULL"))


def downgrade() -> None:
    op.execute("DROP TRIGGER template_versions_kept")
    op.execute(KEPT.format(also=""))
