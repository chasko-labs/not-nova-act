"""Unit 7: eval battery harness. Viewport matrix, tracing+video,
per-case artifacts under artifacts/<case>/<viewport>/."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

VIEWPORTS = {
    "phone": {"width": 480, "height": 800},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1280, "height": 800},
    "wide": {"width": 1920, "height": 1080},
}

ARTIFACT_ROOT = Path(os.environ.get("NOT_NOVA_ACT_ARTIFACTS", "artifacts"))


@pytest.fixture(params=sorted(VIEWPORTS))
def viewport(request):
    return request.param, VIEWPORTS[request.param]


@pytest.fixture()
def cased_page(viewport, request):
    """Yields (page, ctx, events, finalize). Call finalize(case) at test end
    to stop tracing and persist trace.zip + video + console/network logs."""
    name, vp = viewport
    case = request.node.originalname or request.node.name
    outdir = ARTIFACT_ROOT / case / name
    outdir.mkdir(parents=True, exist_ok=True)
    events = {"console": [], "pageerror": [], "requestfailed": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=vp, record_video_dir=str(outdir))
        ctx.tracing.start(screenshots=True, snapshots=True)
        page = ctx.new_page()
        page.on("console", lambda m: events["console"].append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: events["pageerror"].append(str(e)))
        page.on("requestfailed", lambda r: events["requestfailed"].append(r.url))

        def finalize():
            ctx.tracing.stop(path=str(outdir / "trace.zip"))
            (outdir / "console.log").write_text("\n".join(events["console"]))
            (outdir / "pageerrors.log").write_text("\n".join(events["pageerror"]))
            (outdir / "requestfailed.log").write_text("\n".join(events["requestfailed"]))
            shot = outdir / "final.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
            except Exception:
                pass
            ctx.close()
            browser.close()
            return outdir, events

        yield page, finalize
