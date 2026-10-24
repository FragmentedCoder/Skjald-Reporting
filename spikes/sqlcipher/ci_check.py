"""Fail CI unless the SQLCipher check produced the expected results (reads out/report.json)."""

import json
import pathlib
import sys

r = json.loads(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "out/report.json").read_text())
checks = {
    "no SQLite header in the file": r["starts_with_sqlite_header"] is False,
    "no plaintext in the file": r["plaintext_marker_found_in_file"] is False,
    "plain SQLite cannot read it": r["plain_sqlite_can_read"] is not True,
    "wrong key rejected": str(r["wrong_key_rejected"]).startswith("yes"),
    "tampering detected": bool(r["tamper_cipher_integrity_check"]),
    "no errors from concurrent writers": r["concurrent_write_errors"] == 0,
    "backup is consistent": r["backup_integrity_check"] == "ok" and r["backup_cipher_integrity_check_problems"] == 0,
    "backup taken during writes": r["rows_when_backup_started"] <= r["backup_rows"] < r["rows_after_backup_writer"],
    "rekey works": r["opens_with_new_key"] == r["rows_after_backup_writer"] and r["old_key_still_works"] is False,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    print("failed: " + ", ".join(failed))
    sys.exit(1)
print(f"sqlcipher check ok: {len(checks)} checks passed")
