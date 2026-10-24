from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

import app.audit  # noqa: F401  (registers its tables on Base.metadata)
from app.db import Base


def test_the_migrations_build_exactly_the_schema_the_models_describe(engine) -> None:
    with engine.connect() as conn:
        differences = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert differences == []
