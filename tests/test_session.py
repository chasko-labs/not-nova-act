import base64
import json

import pytest

from not_nova_act.session import SessionAssertionError, assert_authenticated_session, decode_jwt_payload


class FakePage:
    def __init__(self, token):
        self.token = token

    def evaluate(self, _expression):
        return self.token


def jwt(payload):
    def segment(value):
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{segment({'alg': 'none'})}.{segment(payload)}.c2lnbmF0dXJl"


def test_session_assertion_accepts_non_expired_app_id_token():
    token = jwt({"exp": 2_000_000_000, "sub": "test-user", "email": "agent@example.test"})
    result = assert_authenticated_session(FakePage(token), now=1_900_000_000)
    assert result["authenticated"] is True
    assert result["subject"] == "test-user"
    assert result["email"] == "agent@example.test"
    assert "token" not in result


def test_session_assertion_rejects_expired_token():
    token = jwt({"exp": 100, "sub": "test-user"})
    with pytest.raises(SessionAssertionError, match="expired"):
        assert_authenticated_session(FakePage(token), now=100)


def test_session_assertion_rejects_missing_token():
    with pytest.raises(SessionAssertionError, match="missing"):
        assert_authenticated_session(FakePage(None))


def test_decode_jwt_payload_rejects_malformed_token():
    with pytest.raises(ValueError):
        decode_jwt_payload("not-a-jwt")
