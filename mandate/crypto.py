"""Signed capability tokens.

A mandate is not just a row in a database — it is a signed token the agent
carries. The payment gateway verifies the signature on every spend, so the
agent cannot edit its own limits, and revocation is enforced server-side
independently of the token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign(payload: dict[str, Any], secret: str) -> str:
    body = _b64e(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    mac = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256)
    return f"{body}.{_b64e(mac.digest())}"


def verify(token: str, secret: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Return (valid, payload, error). Never raises on malformed input."""
    if not token or not isinstance(token, str):
        return False, None, "missing token"
    parts = token.split(".")
    if len(parts) != 2:
        return False, None, "malformed token"
    body, signature = parts
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256)
    expected_sig = _b64e(expected.digest())
    if not hmac.compare_digest(signature, expected_sig):
        return False, None, "signature mismatch"
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return False, None, "payload is not valid JSON"
    if not isinstance(payload, dict):
        return False, None, "payload is not an object"
    return True, payload, None


def token_preview(token: str) -> str:
    if len(token) <= 28:
        return token
    return f"{token[:16]}…{token[-10:]}"


def now() -> float:
    return time.time()
