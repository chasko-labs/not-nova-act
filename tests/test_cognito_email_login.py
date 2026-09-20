from urllib.parse import parse_qs, urlsplit

import pytest

from not_nova_act.cognito_email_login import (
    CognitoChallenge,
    CognitoEmailLoginConfig,
    detect_cognito_challenge,
    prepare_login_url,
)


class FakeLocator:
    def __init__(self, count=0):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self, active_view, passkey=False):
        self.active_view = active_view
        self.passkey = passkey

    def locator(self, selector):
        if selector == f"#{self.active_view}.active":
            return FakeLocator(1)
        if selector == "#btn-method-passkey:not(.hidden)" and self.passkey:
            return FakeLocator(1)
        if selector == "#btn-passkey-quick:not(.hidden)" and self.passkey:
            return FakeLocator(1)
        return FakeLocator(0)


def config():
    return CognitoEmailLoginConfig(
        username="agent@example.test",
        recipient="agent@example.test",
    )


def test_prepare_url_replaces_mom_route_without_triggering_mom_alias():
    prepared = prepare_login_url(config())
    parsed = urlsplit(prepared)
    query = parse_qs(parsed.query)
    assert parsed.path == "/signin/"
    assert query["u"] == ["agent@example.test"]
    assert query["method"] == ["email_code"]
    assert query["redirect"] == ["/mom/"]


def test_personal_gmail_and_mom_alias_are_rejected():
    with pytest.raises(ValueError, match="dedicated test user"):
        CognitoEmailLoginConfig(username="mom")
    with pytest.raises(ValueError, match="personal gmail"):
        CognitoEmailLoginConfig(username="someone@gmail.com")


def test_challenge_detector_recognizes_otp_password_and_passkey():
    assert detect_cognito_challenge(FakePage("view-otp")) == CognitoChallenge.OTP
    assert detect_cognito_challenge(FakePage("view-password")) == CognitoChallenge.PASSWORD
    assert detect_cognito_challenge(FakePage("view-identifier", passkey=True)) == CognitoChallenge.PASSKEY
