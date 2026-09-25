"""Bench UI overhaul checks through not-nova-act's own eval harness.

Converted from the retired raw-Nova-Act runner
(bryanchasko-bench deploy/herald/devenv/tests/nova-act/). Same checks,
same selectors — the only change is the runner: local playwright page via
the cased_page fixture (viewport matrix + tracing + video free).

TIER 1 (unauthenticated) always runs. TIER 2 needs bench test creds in
SSM (/heraldstack/shared/DCODE_TEST_USER + _PASSWORD) and skips cleanly
without them.
"""

from __future__ import annotations

import os

import pytest

BENCH_URL = "https://bryanchasko.com/bench/"
SSM_PREFIX = "/heraldstack/shared/"


def _rgb_parts(bg: str) -> tuple[int, int, int] | None:
    if not bg or not bg.startswith("rgb"):
        return None
    try:
        nums = bg.replace("rgb(", "").replace("rgba(", "").replace(")", "").split(",")
        return int(nums[0].strip()), int(nums[1].strip()), int(nums[2].strip())
    except (ValueError, IndexError):
        return None


def _ssm_creds() -> dict[str, str] | None:
    try:
        import boto3

        ssm = boto3.client("ssm", region_name="us-west-2")
        user = ssm.get_parameter(Name=f"{SSM_PREFIX}DCODE_TEST_USER", WithDecryption=True)
        pw = ssm.get_parameter(Name=f"{SSM_PREFIX}DCODE_TEST_PASSWORD", WithDecryption=True)
        return {"username": user["Parameter"]["Value"], "password": pw["Parameter"]["Value"]}
    except Exception:
        return None


def test_bench_signin_chrome(cased_page):
    """Tier 1: sign-in page renders dark, gold CTA, navy bg, semantic HTML."""
    page, finalize = cased_page
    page.goto(BENCH_URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2000)

    assert page.evaluate("document.body.classList.contains('ready')"), "body.ready missing"

    assert page.evaluate("document.querySelector('main.card') !== null"), "signin card missing"
    assert page.evaluate("document.querySelector('#view-identifier.active') !== null"), \
        "identifier view not active"

    gold = page.evaluate("""(() => {
        const btn = document.querySelector('#btn-continue');
        if (!btn) return null;
        const s = getComputedStyle(btn);
        return {text: btn.textContent.trim(), bg: s.backgroundColor, visible: s.display !== 'none'};
    })()""")
    assert gold and gold["visible"], "continue button missing/hidden"
    parts = _rgb_parts(gold["bg"])
    assert parts and parts[0] > 180 and parts[1] > 140 and parts[2] < 120, \
        f"continue button not gold: {gold}"

    body_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    parts = _rgb_parts(body_bg)
    assert parts and parts[0] < 50 and parts[1] < 50 and parts[2] < 50, \
        f"body not dark navy: {body_bg}"
    assert parts != (0, 0, 0), "body is pure black, want deep navy"

    card_bg = page.evaluate(
        "getComputedStyle(document.querySelector('main.card')).backgroundColor")
    assert "rgba" in (card_bg or "") and "0)" not in (card_bg or ""), \
        f"card not translucent: {card_bg}"

    assert page.evaluate("document.querySelector('main[role]') !== null"), "main[role] missing"
    assert page.evaluate("document.querySelectorAll('label[for]').length") > 0, "no labels"
    assert page.evaluate("document.querySelectorAll('[aria-label]').length") > 5, "few aria-labels"

    outdir, events = finalize()
    assert events["pageerror"] == [], events["pageerror"]


@pytest.mark.skipif(_ssm_creds() is None, reason="needs SSM bench test creds")
def test_bench_dashboard_chrome(cased_page):
    """Tier 2: authenticated dashboard — picker, toggles, theme switch."""
    creds = _ssm_creds()
    assert creds
    page, finalize = cased_page
    page.goto(BENCH_URL, wait_until="networkidle", timeout=60000)
    page.set_default_timeout(30000)

    page.fill("#input-username", creds["username"])
    page.click("#btn-pw-direct")
    page.wait_for_timeout(1000)
    page.fill("#input-password", creds["password"])
    page.click("#btn-pw-submit")
    page.wait_for_timeout(5000)

    picker = page.evaluate("""(() => {
        const el = document.querySelector('#session-picker');
        if (!el) return {found: false};
        const grid = el.querySelector('#session-grid');
        return {found: true, display: getComputedStyle(el).display,
                hasGrid: grid !== null, gridChildren: grid ? grid.children.length : 0};
    })()""")
    assert picker["found"] and picker["display"] != "none", f"picker: {picker}"

    toggle = page.evaluate("""(() => {
        const btn = document.querySelector('#navbar-sidebar-toggle');
        if (!btn) return {found: false};
        const text = btn.textContent.trim();
        return {found: true, guillemet: text.includes('«') || text.includes('»')};
    })()""")
    assert toggle["found"] and toggle["guillemet"], f"toggle: {toggle}"

    bar = page.evaluate("""(() => ({
        bar: document.querySelector('#status-bar') !== null,
        copy: document.querySelector('#btn-copy-statusbar') !== null,
        theme: document.querySelector('#theme-toggle') !== null,
    }))()""")
    assert bar["bar"] and bar["copy"] and bar["theme"], f"status bar: {bar}"

    pre = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.click("#theme-toggle-picker")
    page.wait_for_timeout(1000)
    post = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert pre != post, f"theme toggle no-op: {pre}"

    outdir, events = finalize()
    assert events["pageerror"] == [], events["pageerror"]
