from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

import app.models  # noqa: F401
from app.db import Base, make_engine
from app.migrate import upgrade


def test_the_migrations_build_exactly_the_schema_the_models_describe(engine) -> None:
    with engine.connect() as conn:
        differences = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert differences == []


def test_tables_whose_ids_reach_the_audit_log_never_reuse_an_id(engine) -> None:
    # compare_metadata doesn't look at AUTOINCREMENT, so check the migrations directly.
    autoincrement = {
        table.name for table in Base.metadata.tables.values()
        if table.kwargs.get("sqlite_autoincrement")
    }
    assert autoincrement == {
        "users", "user_sessions", "mfa_factors", "customers", "customer_sites",
        "customer_contacts", "projects",
    }
    with engine.connect() as conn:
        for name in autoincrement:
            sql = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :n"),
                {"n": name},
            ).scalar()
            assert "AUTOINCREMENT" in sql, name


def test_upgrading_keeps_existing_rows(data_dir, master_key_path) -> None:
    """SQLite rebuilds a table to change some constraints, and dropping the old copy
    with foreign keys on deletes every row that cascades from it. Data must survive."""
    engine = make_engine(data_dir, master_key_path)
    upgrade(engine, "0002")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, username, display_name, is_active, failed_sign_ins, created_at)"
            " VALUES (1, 'astrid', 'Astrid', 1, 0, '2026-10-24 12:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO user_sessions (token_hash, user_id, created_at, last_seen_at, expires_at)"
            " VALUES ('h', 1, '2026-10-24 12:00:00', '2026-10-24 12:00:00', '2026-10-25')"
        ))

    upgrade(engine)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM user_sessions")).scalar() == 1
    engine.dispose()


def test_existing_customers_and_projects_are_sealed_on_upgrade(data_dir, master_key_path) -> None:
    """0009 moves names and dates already stored in the clear into the sealed values."""
    from sqlalchemy.orm import Session

    from app.crypto.keys import generate_key, load_master_key, wrap_key
    from app.crypto.sealing import seal
    from app.customers import Customer, Keyring, bound_to

    engine = make_engine(data_dir, master_key_path)
    upgrade(engine, "0008")
    key = generate_key()
    wrapped = wrap_key(load_master_key(master_key_path), key, context=b"skjald/customer-key/1")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO customers (id, name, cvr, wrapped_key, sealed, language,"
            " retention_months, created_at) VALUES (1, 'Nordlys IT ApS', '12345678', :w, :s,"
            " 'da', 12, '2026-10-24 12:00:00')"
        ), {"w": wrapped, "s": seal(key, {"address": "Fjordvej 1"},
                                       bound_to=bound_to(1, "customer", 1))})
        conn.execute(text(
            "INSERT INTO customer_sites (id, customer_id, name, sealed) VALUES (1, 1, 'HQ', :s)"
        ), {"s": seal(key, {"address": "Fjordvej 1"}, bound_to=bound_to(1, "site", 1))})
        conn.execute(text(
            "INSERT INTO projects (id, customer_id, number, name, start_date, classification,"
            " created_at) VALUES (1, 1, 'P-2026-0001', 'Incident', '2026-10-20', 'TLP:RED',"
            " '2026-10-24 12:00:00')"
        ))

    upgrade(engine)

    with Session(engine) as db:
        customer = db.get(Customer, 1)
        keyring = Keyring()
        assert keyring.details(customer) == {
            "name": "Nordlys IT ApS", "cvr": "12345678", "address": "Fjordvej 1"}
        sealer = keyring.sealer(customer)
        site = db.execute(text("SELECT sealed FROM customer_sites")).scalar()
        assert sealer.open("site", 1, site) == {"name": "HQ", "address": "Fjordvej 1"}
        project = db.execute(text("SELECT sealed FROM projects")).scalar()
        assert sealer.open("project", 1, project) == {
            "name": "Incident", "start_date": "2026-10-20", "end_date": None}
        db.commit()
    engine.dispose()
