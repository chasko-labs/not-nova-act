"""playwright cognito email otp login workflow"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .hands import CHROMIUM_GL_ARGS
from .otp import S3OtpReader, build_s3_otp_reader
from .session import assert_authenticated_session

DEFAULT_LOGIN_URL = "https://bryanchasko.com/mom/login"


class CognitoChallenge(StrEnum):
    """signin page challenge state"""

    IDENTIFIER = "identifier"
    METHODS = "methods"
    OTP = "otp"
    PASSWORD = "password"
    PASSKEY = "passkey"
    SUCCESS = "success"
    SIGNED_IN = "signed_in"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CognitoEmailLoginConfig:
    """safe test-user login inputs"""

    username: str
    recipient: str | None = None
    login_url: str = DEFAULT_LOGIN_URL
    redirect_path: str = "/mom/"
    timeout_seconds: float = 180
    otp_timeout_seconds: float = 120
    otp_resend_after_seconds: float | None = 35
    max_otp_resends: int = 1
    clock_skew_seconds: int = 60

    def __post_init__(self) -> None:
        username = self.username.strip().lower()
        if not username or username == "mom":
            raise ValueError("cognito email login requires a dedicated test user")
        domain = username.rsplit("@", 1)[-1]
        if domain in {"gmail.com", "googlemail.com"}:
            raise ValueError("personal gmail mailboxes are not supported")
        recipient = (self.recipient or self.username).strip()
        if not recipient:
            raise ValueError("otp recipient is required")
        if not self.redirect_path.startswith("/") or self.redirect_path.startswith("//"):
            raise ValueError("redirect_path must be an origin-relative path")

    @property
    def otp_recipient(self) -> str:
        return (self.recipient or self.username).strip()


def prepare_login_url(config: CognitoEmailLoginConfig) -> str:
    """route test users directly to signin so the mom alias never sends mail"""
    parsed = urlsplit(config.login_url)
    path = "/signin/" if parsed.path.rstrip("/") == "/mom/login" else parsed.path
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["u"] = [config.username]
    query["method"] = ["email_code"]
    query["redirect"] = [config.redirect_path]
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query, doseq=True), parsed.fragment))


def _is_active(page: Any, view_id: str) -> bool:
    return page.locator(f"#{view_id}.active").count() > 0


def detect_cognito_challenge(page: Any) -> CognitoChallenge:
    """classify the active signin view before an action is dispatched"""
    if _is_active(page, "view-otp"):
        return CognitoChallenge.OTP
    if _is_active(page, "view-password"):
        return CognitoChallenge.PASSWORD
    if _is_active(page, "view-success"):
        return CognitoChallenge.SUCCESS
    if _is_active(page, "view-signed-in"):
        return CognitoChallenge.SIGNED_IN
    if _is_active(page, "view-methods"):
        if page.locator("#btn-method-passkey:not(.hidden)").count() > 0:
            return CognitoChallenge.PASSKEY
        return CognitoChallenge.METHODS
    if _is_active(page, "view-identifier"):
        if page.locator("#btn-passkey-quick:not(.hidden)").count() > 0:
            return CognitoChallenge.PASSKEY
        return CognitoChallenge.IDENTIFIER
    return CognitoChallenge.UNKNOWN


def _wait_for_active_view(page: Any, timeout_ms: int) -> None:
    page.wait_for_function(
        "() => Boolean(document.querySelector('.view.active'))",
        timeout=timeout_ms,
    )


def _status_text(page: Any) -> str:
    return str(page.locator(".view.active .status").first.inner_text())[:300]


def _click_resend(page: Any, timeout_ms: int = 10000) -> None:
    page.wait_for_function(
        "() => { const b = document.querySelector('#btn-resend'); return b && !b.disabled; }",
        timeout=timeout_ms,
    )
    page.locator("#btn-resend").click()


def run_cognito_email_login_on_page(
    page: Any,
    config: CognitoEmailLoginConfig,
    otp_reader: S3OtpReader,
) -> dict[str, Any]:
    """run the login flow in an existing playwright page"""
    baseline = otp_reader.snapshot_keys()
    page.goto(prepare_login_url(config), wait_until="domcontentloaded", timeout=int(config.timeout_seconds * 1000))
    _wait_for_active_view(page, int(config.timeout_seconds * 1000))
    challenge = detect_cognito_challenge(page)
    if challenge == CognitoChallenge.IDENTIFIER:
        page.locator("#input-username").fill(config.username)
        page.locator("#btn-continue").click()
    elif challenge in {CognitoChallenge.METHODS, CognitoChallenge.PASSKEY}:
        if page.locator("#btn-method-otp").count() > 0:
            page.locator("#btn-method-otp").click()
        else:
            page.locator("#input-username").fill(config.username)
            page.locator("#btn-continue").click()
    elif challenge in {CognitoChallenge.OTP, CognitoChallenge.SUCCESS, CognitoChallenge.SIGNED_IN}:
        pass
    else:
        return {
            "status": "error",
            "error_message": f"unsupported cognito signin challenge: {challenge}",
            "challenge": str(challenge),
        }

    if challenge not in {CognitoChallenge.OTP, CognitoChallenge.SUCCESS, CognitoChallenge.SIGNED_IN}:
        try:
            page.wait_for_function(
                "() => Boolean(document.querySelector('#view-otp.active')) || "
                "Boolean(document.querySelector('#view-password.active'))",
                timeout=int(config.timeout_seconds * 1000),
            )
        except Exception as exc:
            return {"status": "error", "error_message": f"otp view did not appear: {_status_text(page)} ({exc})"}
        challenge = detect_cognito_challenge(page)
    if challenge != CognitoChallenge.OTP:
        return {
            "status": "error",
            "error_message": f"expected otp challenge, received {challenge}: {_status_text(page)}",
            "challenge": str(challenge),
        }

    code = otp_reader.wait_for_code(
        config.otp_recipient,
        timeout_seconds=config.otp_timeout_seconds,
        seen_keys=baseline,
        resend=lambda: _click_resend(page),
        resend_after_seconds=config.otp_resend_after_seconds,
        max_resends=config.max_otp_resends,
    )
    if not re.fullmatch(r"[0-9]{8}", code):
        return {"status": "error", "error_message": "otp reader returned a non-eight-digit code"}
    cells = page.locator(".otp-cell")
    if cells.count() != 8:
        return {"status": "error", "error_message": f"expected 8 otp cells, found {cells.count()}"}
    for index, digit in enumerate(code):
        cells.nth(index).fill(digit)

    try:
        page.wait_for_function(
            "(path) => window.location.pathname.startsWith(path) && "
            "Boolean(window.localStorage.getItem('app.idToken'))",
            arg=config.redirect_path,
            timeout=int(config.timeout_seconds * 1000),
        )
        session = assert_authenticated_session(
            page,
            clock_skew_seconds=config.clock_skew_seconds,
        )
    except Exception as exc:
        return {"status": "error", "error_message": f"post-login assertion failed: {exc}"}
    return {
        "status": "completed",
        "final_url": page.url,
        "username": config.username,
        "recipient": config.otp_recipient,
        "challenge": str(CognitoChallenge.OTP),
        "session": session,
    }


def cognito_email_login(
    config: CognitoEmailLoginConfig,
    otp_reader: S3OtpReader,
) -> dict[str, Any]:
    """open chromium and execute the cognito email otp flow"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=CHROMIUM_GL_ARGS)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            try:
                return run_cognito_email_login_on_page(page, config, otp_reader)
            finally:
                browser.close()
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:500]}


def cognito_email_login_from_s3(
    *,
    username: str,
    otp_bucket: str,
    otp_prefix: str,
    recipient: str | None = None,
    login_url: str = DEFAULT_LOGIN_URL,
    redirect_path: str = "/mom/",
    aws_profile: str | None = "aerospaceug-admin",
    aws_region: str = "us-west-2",
    timeout_seconds: float = 180,
    otp_timeout_seconds: float = 120,
) -> dict[str, Any]:
    """construct the configured s3 reader and execute the workflow"""
    config = CognitoEmailLoginConfig(
        username=username,
        recipient=recipient,
        login_url=login_url,
        redirect_path=redirect_path,
        timeout_seconds=timeout_seconds,
        otp_timeout_seconds=otp_timeout_seconds,
    )
    reader = build_s3_otp_reader(
        otp_bucket,
        otp_prefix,
        region=aws_region,
        aws_profile=aws_profile,
    )
    return cognito_email_login(config, reader)
