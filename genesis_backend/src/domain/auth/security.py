import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


PBKDF2_ITERATIONS = 390_000
PBKDF2_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = os.urandom(PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False

    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored_hash.split("$", maxsplit=3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except ValueError:
        return False

    computed_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(computed_digest, expected_digest)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}")


def sign_access_token(payload: dict[str, Any], secret_key: str, expires_in_seconds: int) -> str:
    now = int(time.time())
    merged_payload = {
        **payload,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    body = json.dumps(merged_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body_b64 = _b64url_encode(body)
    signature = hmac.new(
        key=secret_key.encode("utf-8"),
        msg=body_b64.encode("ascii"),
        digestmod=hashlib.sha256,
    ).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{body_b64}.{signature_b64}"


def decode_access_token(token: str, secret_key: str) -> dict[str, Any]:
    try:
        body_b64, signature_b64 = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise ValueError("Invalid token format") from exc

    expected_signature = hmac.new(
        key=secret_key.encode("utf-8"),
        msg=body_b64.encode("ascii"),
        digestmod=hashlib.sha256,
    ).digest()
    provided_signature = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("Invalid token signature")

    payload_raw = _b64url_decode(body_b64)
    payload = json.loads(payload_raw.decode("utf-8"))

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(time.time()):
        raise ValueError("Token expired")

    return payload
