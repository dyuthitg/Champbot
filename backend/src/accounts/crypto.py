"""
Encryption for connected-account auth material.

A LinkedIn session cookie is a bearer credential: anyone holding it *is* the
user. It is therefore Fernet-encrypted before it touches the database, and the
plaintext only ever exists in memory for the duration of a transport call.

The key comes from ``ENCRYPTION_KEY`` (a urlsafe base64 Fernet key). If it is
absent the module refuses to encrypt rather than silently storing plaintext —
except in explicitly-flagged local development, where a deterministic key keeps
the dev loop working without ceremony.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEV_KEY_SEED = "social-bot-linkedin-local-dev"


class EncryptionUnavailable(RuntimeError):
    """No usable encryption key is configured."""


def _dev_key() -> bytes:
    """Deterministic local-only key so `USE_SQLITE=true` dev runs work."""
    digest = hashlib.sha256(_DEV_KEY_SEED.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _load_key() -> bytes:
    configured = os.getenv("ENCRYPTION_KEY", "").strip()
    if configured:
        key = configured.encode()
        # Accept a raw 32-byte secret as well as a proper Fernet key.
        if len(key) != 44:
            key = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
        return key
    if os.getenv("ALLOW_INSECURE_DEV_ENCRYPTION", "").lower() == "true":
        logger.warning(
            "ENCRYPTION_KEY unset; using the insecure local dev key. "
            "Never do this in production."
        )
        return _dev_key()
    raise EncryptionUnavailable(
        "ENCRYPTION_KEY is not set. Generate one with: python -c "
        "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )


def _fernet():
    from cryptography.fernet import Fernet  # lazy: keeps import cost off cold paths

    return Fernet(_load_key())


def generate_key() -> str:
    """Generate a fresh Fernet key (operator convenience)."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def encrypt_auth(payload: Any) -> str:
    """Serialize and encrypt auth material for storage."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return _fernet().encrypt(text.encode()).decode()


def decrypt_auth(blob: Optional[str]) -> Optional[str]:
    """
    Decrypt stored auth material.

    Returns ``None`` when there is nothing stored, and raises on a blob that
    cannot be decrypted (wrong key / tampering) so the caller marks the account
    as needing re-authentication rather than silently doing nothing.
    """
    if not blob:
        return None
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionUnavailable(
            "stored credentials could not be decrypted (key rotated?)"
        ) from exc
