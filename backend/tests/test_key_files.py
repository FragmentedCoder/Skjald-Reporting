import multiprocessing
import os

import pytest

from app.crypto.key_files import load_or_create_database_key
from app.crypto.keys import generate_key


def _write_master_key(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "master.key"
    path.write_bytes(generate_key())
    return path


def test_creates_and_persists_a_wrapped_key(tmp_path) -> None:
    master_key_path = _write_master_key(tmp_path)
    data_dir = tmp_path / "data"

    key = load_or_create_database_key(data_dir, master_key_path)

    assert len(key) == 32
    assert (data_dir / "db.key.enc").exists()
    assert (data_dir / "db.key.enc").stat().st_mode & 0o777 == 0o600


def test_returns_the_same_key_on_a_second_call(tmp_path) -> None:
    master_key_path = _write_master_key(tmp_path)
    data_dir = tmp_path / "data"

    first = load_or_create_database_key(data_dir, master_key_path)
    second = load_or_create_database_key(data_dir, master_key_path)

    assert first == second


def test_different_installs_get_different_keys(tmp_path) -> None:
    key_a = load_or_create_database_key(tmp_path / "a", _write_master_key(tmp_path / "a-etc"))
    key_b = load_or_create_database_key(tmp_path / "b", _write_master_key(tmp_path / "b-etc"))
    assert key_a != key_b


def test_processes_starting_at_once_all_get_the_same_key(tmp_path) -> None:
    master_key_path = _write_master_key(tmp_path)
    data_dir = tmp_path / "data"

    with multiprocessing.get_context("spawn").Pool(8) as pool:
        keys = pool.starmap(load_or_create_database_key, [(data_dir, master_key_path)] * 8)

    assert len(set(keys)) == 1
    assert not list(data_dir.glob(".*.tmp"))


def test_a_key_is_never_readable_more_widely_on_the_way(tmp_path, monkeypatch, set_umask) -> None:
    # No mode can be changed once a file is made and the umask takes nothing away,
    # so the temporary file still has the mode it was made with as it's linked
    # into place: it must be private by then.
    monkeypatch.setattr(os, "chmod", lambda *args, **kwargs: None)
    monkeypatch.setattr(os, "fchmod", lambda *args, **kwargs: None)
    set_umask(0)
    made: list[int] = []
    link = os.link

    def linking(tmp, path) -> None:
        made.append(tmp.stat().st_mode & 0o777)
        link(tmp, path)

    monkeypatch.setattr(os, "link", linking)
    load_or_create_database_key(tmp_path / "data", _write_master_key(tmp_path))
    assert made == [0o600]


@pytest.mark.parametrize("umask", [0o022, 0o077, 0])
def test_a_key_ends_private_under_any_umask(tmp_path, set_umask, umask) -> None:
    set_umask(umask)
    data_dir = tmp_path / "data"
    load_or_create_database_key(data_dir, _write_master_key(tmp_path))
    assert (data_dir / "db.key.enc").stat().st_mode & 0o777 == 0o600


def test_a_temporary_file_left_behind_doesnt_stop_the_next_start(tmp_path) -> None:
    # A start cut short can leave one, and a later process can get the same number.
    master_key_path = _write_master_key(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    left = data_dir / f".db.key.enc.{os.getpid()}.tmp"
    left.write_bytes(b"half a key")
    left.chmod(0o444)
    key = load_or_create_database_key(data_dir, master_key_path)
    assert key == load_or_create_database_key(data_dir, master_key_path)
    assert not list(data_dir.glob(".*.tmp"))
