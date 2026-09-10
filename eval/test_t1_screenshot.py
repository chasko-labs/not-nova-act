"""T1 screenshot: goto example page; full-page screenshot exists; no console errors."""

from pathlib import Path


def test_t1_screenshot(cased_page):
    page, finalize = cased_page
    page.goto("https://example.com", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(1000)
    outdir, events = finalize()
    shots = [p for p in outdir.glob("*.png") if p.stat().st_size > 0]
    assert shots, f"no screenshots in {outdir}"
    assert events["pageerror"] == [], events["pageerror"]
    assert (outdir / "trace.zip").exists()
