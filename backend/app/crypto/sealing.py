"""Sealing record fields with a customer's key.

A sealed value is AES-256-GCM over JSON, bound to the record it belongs to (the
associated data names the customer, the kind of record and its ID), so a sealed
value copied onto another record or another customer won't open.
"""

from __future__ import annotations

import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto.keys import NONCE_LENGTH


def seal(key: bytes, value: dict[str, Any], *, bound_to: bytes) -> bytes:
    nonce = os.urandom(NONCE_LENGTH)
    data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return nonce + AESGCM(key).encrypt(nonce, data, bound_to)


def unseal(key: bytes, sealed: bytes, *, bound_to: bytes) -> dict[str, Any]:
    """Raises cryptography.exceptions.InvalidTag if sealed was changed or moved."""
    nonce, ciphertext = sealed[:NONCE_LENGTH], sealed[NONCE_LENGTH:]
    value = json.loads(AESGCM(key).decrypt(nonce, ciphertext, bound_to))
    if not isinstance(value, dict):
        raise ValueError("A sealed value must be an object.")
    return value
