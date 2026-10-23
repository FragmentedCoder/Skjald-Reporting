# Check: encrypted SQLite with SQLCipher

**Result: SQLCipher does everything Skjald needs.** The database file is unreadable without the key, tampering is detected, several processes write at once without errors, a consistent encrypted backup can be taken while writes continue, and the key can be changed in place. SQLAlchemy works on top unchanged.

Versions: SQLCipher 4.12.0 community, SQLite 3.51.1, sqlcipher3-binary 0.6.0, SQLAlchemy 2.1.6.

| Check | Result |
| --- | --- |
| File header | No "SQLite format 3" header; the file looks like random data |
| Plaintext in the file | A marker string written into 11,500 rows does not appear anywhere in the file |
| Plain SQLite opens it | No: "file is not a database" |
| Wrong key | Rejected |
| One byte changed in the file | Detected: "HMAC verification failed for page 136" (every page carries an HMAC) |
| 4 processes × 250 single-row transactions at once (WAL mode) | 0 errors, 0.9 s |
| Encrypted backup taken while another process keeps writing | Consistent snapshot (11,071 rows; the writer went on to 11,500), integrity checks pass, 0.03 s for 1.1 MB |
| Rekey in place | 0.02 s for 1.1 MB; the new key opens it, the old key no longer does |
| SQLAlchemy ORM: 10,000 rows in one transaction | 1.2 s |
| SQLAlchemy: 1,000 indexed queries | 0.14 s |
| Opening a connection with a raw 256-bit key | 1.4 ms |
| Opening a connection with a passphrase | 129 ms |

## Findings for the real build

- **Use raw 256-bit keys, not passphrases.** A passphrase is stretched with PBKDF2 on every connection, which costs about 129 ms. The database key comes from the key hierarchy as raw bytes anyway, so opening costs 1.4 ms.
- **Connection settings:** `PRAGMA key` first, then `journal_mode = WAL`, `busy_timeout = 30000`, `foreign_keys = ON` and `cipher_memory_security = ON`. SQLAlchemy uses them through a `creator` function.
- **Backups:** `sqlcipher_export()` into a separately keyed file gives a consistent snapshot without stopping the app. restic then encrypts and stores that file, as designed.
- **Health check:** `PRAGMA cipher_integrity_check` verifies every page's HMAC. The weekly restore test runs it on the restored copy.
- **Licence:** SQLCipher Community Edition is BSD-style, compatible with AGPL-3.0.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python check.py
```

The "hmac check failed" lines printed during the run come from the deliberate wrong-key and tamper tests.
