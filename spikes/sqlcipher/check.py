"""Phase 0 check: encrypted SQLite (SQLCipher) from Python, the way Skjald will use it.

Answers:
  - Is the file unreadable without the key, and is a wrong key rejected?
  - Does tampering with the file get detected?
  - Do several processes writing at once work (WAL mode)?
  - Can a consistent, still-encrypted backup be taken while writes continue?
  - Can the key be changed (rekey)?
  - Does SQLAlchemy work on top, and how fast is it?

Usage: python check.py [--out out]
All keys here are throw-away test values generated at run time.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import pathlib
import secrets
import sqlite3
import time

import sqlcipher3
from sqlalchemy import Column, Integer, String, create_engine, select, func
from sqlalchemy.orm import DeclarativeBase, Session

MARKER = "Fjordvik-Logistik-plaintext-marker"


def connect(path: pathlib.Path, key_hex: str, wal: bool = True):
    """Open an encrypted database with a raw 256-bit key (no passphrase stretching on every open)."""
    conn = sqlcipher3.connect(str(path), timeout=30, check_same_thread=False)
    conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    conn.execute("PRAGMA cipher_memory_security = ON")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if wal:
        conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("SELECT count(*) FROM sqlite_master").fetchone()  # fails here if the key is wrong
    return conn


class Base(DeclarativeBase):
    pass


class Finding(Base):
    __tablename__ = "finding"
    id = Column(Integer, primary_key=True)
    customer = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    severity = Column(String, nullable=False)


def writer(path: str, key_hex: str, worker: int, rows: int) -> int:
    conn = connect(pathlib.Path(path), key_hex)
    errors = 0
    for i in range(rows):
        try:
            with conn:  # one short transaction per row, like a busy web app
                conn.execute("INSERT INTO finding (customer, title, severity) VALUES (?, ?, ?)",
                             (f"customer-{worker}", f"finding {i} {MARKER}", "high"))
        except Exception:
            errors += 1
    conn.close()
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out"))
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.db*"):
        f.unlink()
    db = out / "skjald.db"
    key = secrets.token_hex(32)
    report: dict = {"sqlcipher": None, "sqlite": None}

    # 1. SQLAlchemy on top of SQLCipher, bulk insert and lookups
    engine = create_engine("sqlite://", creator=lambda: connect(db, key))
    Base.metadata.create_all(engine)
    with engine.connect() as c:
        report["sqlcipher"] = c.exec_driver_sql("PRAGMA cipher_version").scalar()
        report["sqlite"] = c.exec_driver_sql("SELECT sqlite_version()").scalar()
    start = time.perf_counter()
    with Session(engine) as s, s.begin():
        s.add_all(Finding(customer=f"customer-{i % 50}", title=f"finding {i} {MARKER}", severity="high")
                  for i in range(10_000))
    report["insert_10k_rows_one_transaction_s"] = round(time.perf_counter() - start, 3)
    start = time.perf_counter()
    with Session(engine) as s:
        for i in range(1_000):
            s.execute(select(func.count()).select_from(Finding).where(Finding.customer == f"customer-{i % 50}")).scalar()
    report["1k_indexed_queries_s"] = round(time.perf_counter() - start, 3)
    engine.dispose()

    # 2. Opening cost: raw key vs passphrase (PBKDF2 runs on every open with a passphrase)
    start = time.perf_counter()
    for _ in range(20):
        connect(db, key).close()
    report["open_with_raw_key_ms"] = round((time.perf_counter() - start) / 20 * 1000, 2)
    pw_db = out / "passphrase.db"
    c = sqlcipher3.connect(str(pw_db))
    c.execute("PRAGMA key = 'a test passphrase'")
    c.execute("CREATE TABLE t (x)")
    c.commit()
    c.close()
    start = time.perf_counter()
    for _ in range(5):
        c = sqlcipher3.connect(str(pw_db))
        c.execute("PRAGMA key = 'a test passphrase'")
        c.execute("SELECT count(*) FROM t").fetchone()
        c.close()
    report["open_with_passphrase_ms"] = round((time.perf_counter() - start) / 5 * 1000, 1)

    # 3. Concurrent writers in separate processes (WAL)
    start = time.perf_counter()
    with mp.get_context("spawn").Pool(4) as pool:
        errors = pool.starmap(writer, [(str(db), key, w, 250) for w in range(4)])
    report["4_processes_x_250_single_row_transactions_s"] = round(time.perf_counter() - start, 3)
    report["concurrent_write_errors"] = sum(errors)
    conn = connect(db, key)
    report["rows_after_concurrent_writes"] = conn.execute("SELECT count(*) FROM finding").fetchone()[0]

    # 4. Consistent encrypted backup while a writer keeps going
    backup = out / "backup.db"
    backup_key = secrets.token_hex(32)
    before = report["rows_after_concurrent_writes"]
    bg = mp.get_context("spawn").Process(target=writer, args=(str(db), key, 99, 500))
    bg.start()
    deadline = time.time() + 20
    while conn.execute("SELECT count(*) FROM finding").fetchone()[0] < before + 50 and time.time() < deadline:
        time.sleep(0.01)  # wait until the writer is mid-way, so the backup really runs during writes
    report["rows_when_backup_started"] = conn.execute("SELECT count(*) FROM finding").fetchone()[0]
    start = time.perf_counter()
    conn.execute(f"ATTACH DATABASE '{backup}' AS backup KEY \"x'{backup_key}'\"")
    conn.execute("SELECT sqlcipher_export('backup')")
    conn.execute("DETACH DATABASE backup")
    report["backup_export_s"] = round(time.perf_counter() - start, 3)
    bg.join()
    b = connect(backup, backup_key, wal=False)
    report["backup_integrity_check"] = b.execute("PRAGMA integrity_check").fetchone()[0]
    report["backup_cipher_integrity_check_problems"] = len(b.execute("PRAGMA cipher_integrity_check").fetchall())
    report["backup_rows"] = b.execute("SELECT count(*) FROM finding").fetchone()[0]
    b.close()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    report["rows_after_backup_writer"] = conn.execute("SELECT count(*) FROM finding").fetchone()[0]
    conn.close()

    # 5. The file at rest: no header, no plaintext, unreadable without the key
    raw = db.read_bytes()
    report["db_size_mb"] = round(len(raw) / 1e6, 2)
    report["starts_with_sqlite_header"] = raw.startswith(b"SQLite format 3")
    report["plaintext_marker_found_in_file"] = MARKER.encode() in raw
    try:
        sqlite3.connect(db).execute("SELECT count(*) FROM sqlite_master").fetchone()
        report["plain_sqlite_can_read"] = True
    except sqlite3.DatabaseError as exc:
        report["plain_sqlite_can_read"] = f"no ({exc})"
    try:
        connect(db, secrets.token_hex(32)).close()
        report["wrong_key_rejected"] = False
    except Exception as exc:
        report["wrong_key_rejected"] = f"yes ({type(exc).__name__}: {exc})"

    # 6. Tampering: flip one byte in a data page of a copy and check
    tampered = out / "tampered.db"
    data = bytearray(raw)
    data[len(data) // 2] ^= 0x01
    tampered.write_bytes(data)
    t = connect(tampered, key, wal=False)
    report["tamper_cipher_integrity_check"] = [row[0] for row in t.execute("PRAGMA cipher_integrity_check").fetchall()][:2]
    t.close()

    # 7. Rekey: change the key in place
    new_key = secrets.token_hex(32)
    conn = connect(db, key, wal=False)
    conn.execute("PRAGMA journal_mode = DELETE")
    start = time.perf_counter()
    conn.execute(f"PRAGMA rekey = \"x'{new_key}'\"")
    report["rekey_s"] = round(time.perf_counter() - start, 3)
    conn.close()
    report["opens_with_new_key"] = connect(db, new_key).execute("SELECT count(*) FROM finding").fetchone()[0]
    try:
        connect(db, key).close()
        report["old_key_still_works"] = True
    except Exception:
        report["old_key_still_works"] = False

    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
