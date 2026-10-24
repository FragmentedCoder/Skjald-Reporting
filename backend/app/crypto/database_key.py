from __future__ import annotations

import os
from pathlib import Path

from app.crypto.keys import generate_key, load_master_key, unwrap_key, wrap_key

DATABASE_KEY_CONTEXT = b"skjald/database-key"


def load_or_create_database_key(data_dir: str | Path, master_key_path: str | Path) -> bytes:
    """The database key, wrapped by the master key and persisted in the data directory.

    The wrapped form travels safely in backups: without /etc/skjald/master.key it
    decrypts nothing.
    """
    master_key = load_master_key(master_key_path)
    wrapped_path = Path(data_dir) / "db.key.enc"
    if not wrapped_path.exists():
        wrapped = wrap_key(master_key, generate_key(), context=DATABASE_KEY_CONTEXT)
        _create_once(wrapped_path, wrapped)
    return unwrap_key(master_key, wrapped_path.read_bytes(), context=DATABASE_KEY_CONTEXT)


def _create_once(path: Path, data: bytes) -> None:
    """Write data to path unless it already exists.

    The app and the worker can start at the same moment on a fresh install. If
    each wrote its own key, the database would be created under one key and the
    other would be left on disk, and the database could never be opened again.
    A hard link either creates the file whole or fails, so the first one wins
    and everyone reads the winner's key back.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    tmp.chmod(0o600)
    try:
        os.link(tmp, path)
    except FileExistsError:
        pass
    finally:
        tmp.unlink()
