"""Extension loading: allowlisted unpacked MV3 dirs drive chrome-extension:// URLs.

_resolve_extension is pure validation (no browser). The two end-to-end tests
launch a real browser with the stub extension and prove the driven page loads
under its chrome-extension:// origin. No model calls.
"""

from pathlib import Path

import pytest

import not_nova_act.hands as hands
from not_nova_act.hands import (
    _launch,
    _resolve_extension,
    browser_check_page,
    browser_take_screenshot,
)
from playwright.sync_api import sync_playwright

STUB = Path(__file__).parent / "fixtures" / "stub-extension"
# Pinned by the "key" field in the stub manifest (same mechanism production
# unpacked extensions use for stable IDs).
STUB_ID = "jeibmhjmfgkbgganpdnheefdefodljje"
STUB_PAGE = f"chrome-extension://{STUB_ID}/hello.html"


@pytest.fixture()
def ext_root(monkeypatch, tmp_path):
    root = tmp_path / "ext-root"
    (root / "stub").mkdir(parents=True)
    for f in STUB.iterdir():
        (root / "stub" / f.name).write_bytes(f.read_bytes())
    monkeypatch.setattr(hands, "EXTENSION_ROOT", str(root))
    return root


def test_resolve_none_is_off(monkeypatch):
    monkeypatch.setattr(hands, "EXTENSION_ROOT", "")
    assert _resolve_extension(None) is None
    assert _resolve_extension("") is None


def test_resolve_rejected_when_root_unset(monkeypatch):
    monkeypatch.setattr(hands, "EXTENSION_ROOT", "")
    with pytest.raises(ValueError, match="allowlisted"):
        _resolve_extension("/some/ext")


def test_resolve_rejects_outside_root(ext_root):
    with pytest.raises(ValueError, match="outside allowlisted root"):
        _resolve_extension("/tmp")


def test_resolve_rejects_missing_manifest(ext_root):
    with pytest.raises(ValueError, match="manifest.json"):
        _resolve_extension(".")


def test_resolve_accepts_stub(ext_root):
    assert _resolve_extension("stub") == ext_root / "stub"


def test_screenshot_extension_page(ext_root):
    res = browser_take_screenshot(
        STUB_PAGE, wait_seconds=1, extension_path="stub")
    assert res["status"] == "completed", res
    assert Path(res["screenshot_path"]).stat().st_size > 0
    assert res["final_url"].startswith("chrome-extension://")


def test_check_page_extension_dom(ext_root):
    res = browser_check_page(
        STUB_PAGE,
        [{"type": "text_contains", "selector": "h1",
          "expected": "hello from stub extension",
          "description": "stub h1 readable"}],
        wait_seconds=1, extension_path="stub")
    assert res["status"] == "completed", res
    assert res["all_passed"], res["results"]


def test_mobile_with_extension_errors(ext_root):
    res = browser_take_screenshot(
        "https://example.com", wait_seconds=0,
        mobile=True, extension_path="stub")
    assert res["status"] == "error", res
    assert "mobile" in res["error_message"]


def test_launch_without_extension_unchanged():
    with sync_playwright() as p:
        launched = _launch(p)
        try:
            assert launched.__class__.__name__ == "Browser"
        finally:
            launched.close()
