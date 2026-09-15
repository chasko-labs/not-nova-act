"""ses inbound s3 email otp reader"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from io import BytesIO
from typing import Any, Callable


class OtpReaderError(RuntimeError):
    """base error for otp mailbox reads"""


class OtpCodeTimeout(OtpReaderError, TimeoutError):
    """no matching otp arrived before the deadline"""


@dataclass(frozen=True)
class S3OtpConfig:
    """configuration for the ses inbound s3 receipt"""

    bucket: str
    prefix: str
    region: str = "us-west-2"
    aws_profile: str | None = "aerospaceug-admin"


@dataclass(frozen=True)
class OtpMessage:
    """parsed otp message metadata"""

    key: str
    recipient: str
    code: str
    last_modified: datetime | None = None


_CODE_PATTERNS = (
    re.compile(
        r"\b(?:verification|confirmation|security|one[-\s]?time|otp)?\s*"
        r"(?:code|passcode)\s*(?:is|:|-)?\s*([0-9]{8})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b([0-9]{8})\b"),
)
_TAG_RE = re.compile(r"<[^>]+>")


def _normalise_address(value: str) -> str:
    return value.strip().lower()


def _normalise_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _message_body(message: Any) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() != "text":
                continue
            try:
                parts.append(str(part.get_content()))
            except (LookupError, UnicodeError):
                payload = part.get_payload(decode=True) or b""
                parts.append(payload.decode("utf-8", errors="replace"))
    else:
        try:
            parts.append(str(message.get_content()))
        except (LookupError, UnicodeError):
            payload = message.get_payload(decode=True) or b""
            parts.append(payload.decode("utf-8", errors="replace"))
    return html.unescape(_TAG_RE.sub(" ", "\n".join(parts)))


def _message_recipients(message: Any) -> set[str]:
    values: list[str] = []
    for header in ("to", "delivered-to", "x-original-to", "envelope-to"):
        values.extend(message.get_all(header, []))
    return {_normalise_address(address) for _, address in getaddresses(values) if address}


def _extract_code(text: str) -> str | None:
    for pattern in _CODE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            if pattern is _CODE_PATTERNS[1] and len(set(matches)) != 1:
                continue
            return matches[-1]
    return None


class S3OtpReader:
    """poll raw ses messages stored under an s3 prefix"""

    def __init__(
        self,
        config: S3OtpConfig,
        client: Any | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if not config.bucket:
            raise ValueError("otp s3 bucket is required")
        self.config = config
        self._client = client
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            session = boto3.Session(
                profile_name=self.config.aws_profile,
                region_name=self.config.region,
            )
            self._client = session.client("s3")
        return self._client

    def _list_objects(self) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self.config.bucket,
                "Prefix": self.config.prefix,
            }
            if token:
                kwargs["ContinuationToken"] = token
            response = self.client.list_objects_v2(**kwargs)
            objects.extend(response.get("Contents", []))
            if not response.get("IsTruncated"):
                return objects
            token = response.get("NextContinuationToken")
            if not token:
                return objects

    def snapshot_keys(self) -> set[str]:
        """return current object keys to exclude pre-existing messages"""
        return {str(obj["Key"]) for obj in self._list_objects() if obj.get("Key")}

    def _read_message(self, obj: dict[str, Any], wanted: str | None = None) -> OtpMessage | None:
        key = str(obj.get("Key", ""))
        if not key:
            return None
        response = self.client.get_object(Bucket=self.config.bucket, Key=key)
        body = response["Body"].read()
        if isinstance(body, str):
            body = body.encode()
        message = BytesParser(policy=policy.default).parse(BytesIO(body))
        recipients = _message_recipients(message)
        if wanted and _normalise_address(wanted) not in recipients:
            return None
        subject = str(message.get("subject", ""))
        code = _extract_code(f"{subject}\n{_message_body(message)}")
        if not code:
            return None
        recipient = next(iter(recipients), "")
        return OtpMessage(
            key=key,
            recipient=recipient,
            code=code,
            last_modified=_normalise_datetime(obj.get("LastModified")),
        )

    def _newest_message(
        self,
        recipient: str,
        seen_keys: set[str],
        after: datetime | None,
    ) -> OtpMessage | None:
        candidates: list[OtpMessage] = []
        for obj in self._list_objects():
            key = str(obj.get("Key", ""))
            if not key or key in seen_keys:
                continue
            modified = _normalise_datetime(obj.get("LastModified"))
            if after and modified and modified <= _normalise_datetime(after):
                continue
            message = self._read_message(obj, wanted=recipient)
            if not message:
                continue
            candidates.append(message)
        return max(
            candidates,
            key=lambda item: item.last_modified or datetime.min.replace(tzinfo=timezone.utc),
            default=None,
        )

    def wait_for_code(
        self,
        recipient: str,
        *,
        timeout_seconds: float = 120,
        poll_interval_seconds: float = 1,
        max_poll_interval_seconds: float = 10,
        backoff_factor: float = 1.5,
        seen_keys: set[str] | None = None,
        after: datetime | None = None,
        resend: Callable[[], Any] | None = None,
        resend_after_seconds: float | None = None,
        max_resends: int = 1,
    ) -> str:
        """poll until a new matching code arrives, optionally invoking resend"""
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        if poll_interval_seconds <= 0 or max_poll_interval_seconds <= 0:
            raise ValueError("poll intervals must be positive")
        started = self._monotonic()
        deadline = started + timeout_seconds
        seen = set(seen_keys or set())
        interval = poll_interval_seconds
        resend_count = 0
        while True:
            now = self._monotonic()
            if (
                resend
                and resend_after_seconds is not None
                and resend_count < max_resends
                and now - started >= resend_after_seconds
            ):
                try:
                    resend()
                except Exception as exc:
                    raise OtpReaderError(f"resend failed: {exc}") from exc
                resend_count += 1
                started = now
                deadline = max(deadline, now + timeout_seconds)
            message = self._newest_message(recipient, seen, after)
            if message:
                return message.code
            if now >= deadline:
                raise OtpCodeTimeout(
                    f"no 8-digit otp for {recipient} in s3://{self.config.bucket}/{self.config.prefix}"
                )
            self._sleep(min(interval, deadline - now))
            interval = min(interval * backoff_factor, max_poll_interval_seconds)


def build_s3_otp_reader(
    bucket: str,
    prefix: str,
    *,
    region: str = "us-west-2",
    aws_profile: str | None = "aerospaceug-admin",
) -> S3OtpReader:
    """build a reader without embedding credentials or mailbox state"""
    return S3OtpReader(S3OtpConfig(bucket, prefix, region, aws_profile))
