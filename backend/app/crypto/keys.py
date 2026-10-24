"""Envelope encryption for Skjald's key hierarchy (see docs/architecture.md).

The master key never leaves /etc/skjald; every other key (database,
per-customer, backup) is generated at random and stored only in its
wrapped form, decryptable solely by whoever holds the master key.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_LENGTH = 32
NONCE_LENGTH = 12


def generate_key() -> bytes:
    """A fresh random 256-bit key, suitable for a database, customer or backup key."""
    return os.urandom(KEY_LENGTH)


def load_master_key(path: str | Path) -> bytes:
    data = Path(path).read_bytes()
    if len(data) != KEY_LENGTH:
        raise ValueError(f"Master key at {path} must be {KEY_LENGTH} bytes, found {len(data)}.")
    return data


def wrap_key(master_key: bytes, plaintext_key: bytes) -> bytes:
    """Encrypt plaintext_key under the master key. The result is safe to store at rest."""
    nonce = os.urandom(NONCE_LENGTH)
    ciphertext = AESGCM(master_key).encrypt(nonce, plaintext_key, None)
    return nonce + ciphertext


def unwrap_key(master_key: bytes, wrapped: bytes) -> bytes:
    """Reverse wrap_key. Raises cryptography.exceptions.InvalidTag if wrapped was tampered with."""
    nonce, ciphertext = wrapped[:NONCE_LENGTH], wrapped[NONCE_LENGTH:]
    return AESGCM(master_key).decrypt(nonce, ciphertext, None)
