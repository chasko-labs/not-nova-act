"""authenticated browser session assertions"""

from __future__ import annotations

import base64
import json
import time
from typing import Any


class SessionAssertionError(RuntimeError):
    """browser session is missing or has an invalid id token"""


def _decode_bytes(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + padding).encode("ascii"))


def _decode_segment(segment: str) -> dict[str, Any]:
    value = json.loads(_decode_bytes(segment).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("jwt segment is not an object")
    return value


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """decode a jwt payload without claiming signature verification"""
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("id token is not a three-segment jwt")
    _decode_segment(parts[0])
    payload = _decode_segment(parts[1])
    _decode_bytes(parts[2])
    return payload


def assert_authenticated_session(
    page: Any,
    *,
    clock_skew_seconds: int = 60,
    now: float | None = None,
) -> dict[str, Any]:
    """assert a structurally valid, non-expired app.idToken in localstorage"""
    token = page.evaluate("() => window.localStorage.getItem('app.idToken')")
    if not token:
        raise SessionAssertionError("localStorage app.idToken is missing")
    try:
        claims = decode_jwt_payload(str(token))
        expires_at = float(claims["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SessionAssertionError(f"localStorage app.idToken is invalid: {exc}") from exc
    current_time = time.time() if now is None else now
    if expires_at <= current_time + clock_skew_seconds:
        raise SessionAssertionError("localStorage app.idToken is expired or too close to expiry")
    return {
        "authenticated": True,
        "token_expires_at": expires_at,
        "subject": claims.get("sub"),
        "email": claims.get("email"),
    }
