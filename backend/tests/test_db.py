import sqlite3

from sqlalchemy import text

from app.crypto.keys import generate_key
from app.db import check_integrity, make_engine


def _master_key_path(tmp_path):
    path = tmp_path / "master.key"
    path.write_bytes(generate_key())
    return path


def test_the_database_file_is_encrypted_at_rest(tmp_path) -> None:
    master_key_path = _master_key_path(tmp_path)
    data_dir = tmp_path / "data"
    engine = make_engine(data_dir, master_key_path)

    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE t (x TEXT)"))
        conn.execute(text("INSERT INTO t VALUES ('plaintext-marker')"))
        conn.commit()
    engine.dispose()

    raw = (data_dir / "skjald.db").read_bytes()
    assert not raw.startswith(b"SQLite format 3")
    assert b"plaintext-marker" not in raw

    try:
        plain = sqlite3.connect(str(data_dir / "skjald.db"))
        plain.execute("SELECT count(*) FROM sqlite_master").fetchone()
        plain_sqlite_opened = True
    except sqlite3.DatabaseError:
        plain_sqlite_opened = False
    assert not plain_sqlite_opened


def test_reopening_reuses_the_same_key_and_data(tmp_path) -> None:
    master_key_path = _master_key_path(tmp_path)
    data_dir = tmp_path / "data"

    engine_1 = make_engine(data_dir, master_key_path)
    with engine_1.connect() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.execute(text("INSERT INTO t VALUES (1)"))
        conn.commit()
    engine_1.dispose()

    engine_2 = make_engine(data_dir, master_key_path)
    with engine_2.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM t")).scalar() == 1
    engine_2.dispose()


def test_check_integrity_reports_no_problems_on_a_fresh_database(tmp_path) -> None:
    engine = make_engine(tmp_path / "data", _master_key_path(tmp_path))
    assert check_integrity(engine) == []
