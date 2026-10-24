import pytest
from cryptography.exceptions import InvalidTag

from app.crypto.keys import generate_key, load_master_key, unwrap_key, wrap_key


def test_generate_key_is_32_bytes_and_random() -> None:
    assert len(generate_key()) == 32
    assert generate_key() != generate_key()


def test_wrap_and_unwrap_round_trip() -> None:
    master_key = generate_key()
    plaintext = generate_key()
    assert unwrap_key(master_key, wrap_key(master_key, plaintext)) == plaintext


def test_unwrap_detects_tampering() -> None:
    master_key = generate_key()
    wrapped = bytearray(wrap_key(master_key, generate_key()))
    wrapped[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        unwrap_key(master_key, bytes(wrapped))


def test_unwrap_rejects_the_wrong_master_key() -> None:
    wrapped = wrap_key(generate_key(), generate_key())
    with pytest.raises(InvalidTag):
        unwrap_key(generate_key(), wrapped)


def test_load_master_key_round_trips_from_disk(tmp_path) -> None:
    path = tmp_path / "master.key"
    key = generate_key()
    path.write_bytes(key)
    assert load_master_key(path) == key


def test_load_master_key_rejects_the_wrong_length(tmp_path) -> None:
    path = tmp_path / "master.key"
    path.write_bytes(b"too short")
    with pytest.raises(ValueError, match="32 bytes"):
        load_master_key(path)
