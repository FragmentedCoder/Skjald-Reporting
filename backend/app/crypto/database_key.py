from __future__ import annotations

from pathlib import Path

from app.crypto.keys import generate_key, load_master_key, unwrap_key, wrap_key


def load_or_create_database_key(data_dir: str | Path, master_key_path: str | Path) -> bytes:
    """The database key, wrapped by the master key and persisted in the data directory.

    The wrapped form travels safely in backups: without /etc/skjald/master.key it
    decrypts nothing.
    """
    master_key = load_master_key(master_key_path)
    wrapped_path = Path(data_dir) / "db.key.enc"

    if wrapped_path.exists():
        return unwrap_key(master_key, wrapped_path.read_bytes())

    key = generate_key()
    wrapped_path.parent.mkdir(parents=True, exist_ok=True)
    wrapped_path.write_bytes(wrap_key(master_key, key))
    wrapped_path.chmod(0o600)
    return key
