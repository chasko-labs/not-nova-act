from datetime import datetime, timezone
from io import BytesIO

import pytest

from not_nova_act.otp import OtpCodeTimeout, S3OtpConfig, S3OtpReader


class FakeS3:
    def __init__(self, messages=None):
        self.messages = messages or {}

    def list_objects_v2(self, **_kwargs):
        return {
            "Contents": [
                {"Key": key, "LastModified": value[0]}
                for key, value in self.messages.items()
            ],
            "IsTruncated": False,
        }

    def get_object(self, *, Bucket, Key):
        del Bucket
        return {"Body": BytesIO(self.messages[Key][1])}


def message(to, code):
    return f"From: no-reply@example.com\nTo: {to}\nSubject: your verification code\n\nYour verification code is {code}\n".encode()


def reader(client):
    return S3OtpReader(
        S3OtpConfig("otp-bucket", "inbound/test/"),
        client=client,
        sleep_fn=lambda _seconds: None,
    )


def test_reader_returns_newest_code_for_requested_recipient():
    client = FakeS3(
        {
            "inbound/test/old.eml": (
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                message("other@example.test", "11111111"),
            ),
            "inbound/test/new.eml": (
                datetime(2026, 1, 2, tzinfo=timezone.utc),
                message("agent@example.test", "22222222"),
            ),
        }
    )
    assert reader(client).wait_for_code("agent@example.test") == "22222222"


def test_reader_excludes_baseline_and_handles_resend():
    client = FakeS3()
    otp_reader = reader(client)

    def resend():
        client.messages["inbound/test/resend.eml"] = (
            datetime(2026, 1, 3, tzinfo=timezone.utc),
            message("agent@example.test", "33333333"),
        )

    assert otp_reader.wait_for_code(
        "agent@example.test",
        timeout_seconds=1,
        resend=resend,
        resend_after_seconds=0,
    ) == "33333333"


def test_reader_times_out_without_a_new_message():
    with pytest.raises(OtpCodeTimeout):
        reader(FakeS3()).wait_for_code("agent@example.test", timeout_seconds=0)


def test_snapshot_keys_can_seed_a_new_message_boundary():
    client = FakeS3(
        {
            "inbound/test/existing.eml": (
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                message("agent@example.test", "44444444"),
            )
        }
    )
    otp_reader = reader(client)
    baseline = otp_reader.snapshot_keys()
    with pytest.raises(OtpCodeTimeout):
        otp_reader.wait_for_code("agent@example.test", timeout_seconds=0, seen_keys=baseline)
