from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


_ENCRYPTED_PREFIX = "enc::"


def _build_fernet_key() -> bytes:
    secret_key = str(getattr(settings, "SECRET_KEY", "") or "").encode()
    digest = hashlib.sha256(secret_key).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    return Fernet(_build_fernet_key())


def is_encrypted_secret(value: object) -> bool:
    raw_value = str(value or "")
    return raw_value.startswith(_ENCRYPTED_PREFIX)


def encrypt_secret(value: object) -> str:
    raw_value = str(value or "")
    if not raw_value:
        return ""
    if is_encrypted_secret(raw_value):
        return raw_value

    encrypted = _get_fernet().encrypt(raw_value.encode()).decode()
    return f"{_ENCRYPTED_PREFIX}{encrypted}"


def decrypt_secret(value: object) -> str:
    raw_value = str(value or "")
    if not raw_value:
        return ""
    if not is_encrypted_secret(raw_value):
        return raw_value

    token = raw_value.removeprefix(_ENCRYPTED_PREFIX)
    try:
        decrypted = _get_fernet().decrypt(token.encode())
        return decrypted.decode()
    except (InvalidToken, ValueError):
        return ""
