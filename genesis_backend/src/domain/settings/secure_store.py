import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.AUTH_SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_mapping(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def decrypt_mapping(encrypted_payload: str | None) -> dict[str, Any]:
    if not encrypted_payload:
        return {}
    try:
        decrypted = _fernet().decrypt(encrypted_payload.encode("utf-8"))
        value = json.loads(decrypted.decode("utf-8"))
        if isinstance(value, dict):
            return value
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return {}
