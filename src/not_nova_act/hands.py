"""Unit 1: Playwright hands + model-free tools. No GPU, no model calls."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
SCREENSHOT_DIR = Path(os.environ.get("NOT_NOVA_ACT_SCREENSHOT_DIR", "/tmp/not-nova-act-shots"))
HF_HUB_CACHE = Path(os.environ.get("HF_HUB_CACHE", str(Path.home() / ".cache/huggingface/hub")))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

ALIAS_MAP = {"latest-vision": "qwen3-vl:8b"}


@dataclass
class StepResult:
    ok: bool
    observation: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


def _shot_path(prefix: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENSHOT_DIR / f"{prefix}-{int(time.time() * 1000)}.png"


def _cap_width(path: Path, max_width: int) -> dict[str, int]:
    """Downscale in place, aspect preserved. Returns final dims."""
    from PIL import Image

    with Image.open(path) as im:
        w, h = im.size
        if w > max_width:
            im = im.resize((max_width, int(h * max_width / w)))
            im.save(path)
            w, h = im.size
        return {"width": w, "height": h}


def compress_image(path: Path, fmt: str = "jpeg", quality: int = 70) -> dict[str, Any]:
    """Save a compressed sibling `<stem>.min.<fmt>` next to path.
    JPEG q70 is typically 5-10x smaller than PNG screenshots — the form
    vision contexts should carry instead of raw PNGs."""
    from PIL import Image

    path = Path(path)

    if fmt not in ("jpeg", "png"):
        return {"status": "error", "error_message": f"unknown format {fmt}"}
    try:
        with Image.open(path) as im:
            rgb = im.convert("RGB")
            ext = "jpg" if fmt == "jpeg" else "png"
            out = path.with_name(f"{path.stem}.min.{ext}")
            save_kw: dict[str, Any] = {"quality": quality} if fmt == "jpeg" else {}
            rgb.save(out, **save_kw)
        return {"status": "completed", "compressed_path": str(out),
                "bytes": out.stat().st_size,
                "source_bytes": path.stat().st_size}
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:200]}


def browser_take_screenshot(
    url: str,
    wait_seconds: int = 3,
    full_page: bool = True,
    viewport: dict[str, int] | None = None,
    max_width: int | None = None,
) -> dict[str, Any]:
    """Navigate + capture. Returns completed envelope, never raises.

    max_width downscales the saved PNG (aspect preserved) so the file can
    be attached directly to a vision context (most readers cap at 2000px).
    None keeps full resolution for artifact evidence.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=viewport or DEFAULT_VIEWPORT)
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(wait_seconds * 1000)
            path = _shot_path("shot")
            page.screenshot(path=str(path), full_page=full_page)
            dims: dict[str, int] | None = None
            if max_width is not None:
                dims = _cap_width(path, max_width)
            result = {
                "status": "completed",
                "screenshot_path": str(path),
                "page_title": page.title(),
                "final_url": page.url,
                "viewport": viewport or DEFAULT_VIEWPORT,
            }
            if dims is not None:
                result["image_size"] = dims
            browser.close()
            return result
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)}


def run_checks(page, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Run deterministic checks against an already-open page (session-aware
    assertions — beyond the navigate-then-check shape)."""
    results = [_run_check(page, c) for c in checks]
    passed = sum(1 for r in results if r["passed"])
    return {"status": "completed", "checks_passed": passed,
            "checks_total": len(results), "all_passed": passed == len(results),
            "results": results}


def _run_check(page, check: dict[str, Any]) -> dict[str, Any]:
    ctype = check.get("type", "exists")
    selector = check.get("selector", "")
    expected = check.get("expected")
    try:
        if ctype == "exists":
            passed = page.locator(selector).count() > 0
            actual = f"count={page.locator(selector).count()}"
        elif ctype == "visible":
            passed = page.locator(selector).is_visible()
            actual = f"visible={passed}"
        elif ctype == "text_contains":
            actual = page.locator(selector).first.inner_text()
            passed = str(expected) in actual
        elif ctype == "text_eq":
            actual = page.locator(selector).first.inner_text()
            passed = actual.strip() == str(expected).strip()
        elif ctype == "count_eq":
            actual = page.locator(selector).count()
            passed = actual == int(expected)
        elif ctype == "attr_eq":
            actual = page.locator(selector).first.get_attribute(check.get("attr", ""))
            passed = actual == expected
        elif ctype == "a11y_role":
            actual = page.get_by_role(check.get("role", "button"), name=expected).count()
            passed = actual > 0
        elif ctype == "evaluate":
            actual = page.evaluate(check.get("expression", "document.title"))
            passed = (actual == expected) if expected is not None else True
        else:
            return {"description": check.get("description", ctype), "type": ctype,
                    "passed": False, "actual": f"unknown check type: {ctype}"}
        return {"description": check.get("description", ctype), "type": ctype,
                "passed": bool(passed), "actual": str(actual)[:500]}
    except Exception as exc:
        return {"description": check.get("description", ctype), "type": ctype,
                "passed": False, "actual": f"check raised: {exc}"}


def browser_check_page(
    url: str,
    checks: list[dict[str, Any]],
    wait_seconds: int = 3,
    timeout_seconds: int = 120,
    viewport: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Deterministic DOM assertions. No model. Returns completed envelope.

    viewport sets the render width (e.g. {"width": 375, "height": 812} for
    mobile). None keeps DEFAULT_VIEWPORT (1280x800) for backward compat.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=viewport or DEFAULT_VIEWPORT)
            page.goto(url, wait_until="networkidle", timeout=timeout_seconds * 1000)
            page.wait_for_timeout(wait_seconds * 1000)
            out = run_checks(page, checks)
            browser.close()
        out["url"] = url
        return out
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)}


def browser_list_models() -> dict[str, Any]:
    """Local registry: ollama models + HF cache scan + alias map. No model."""
    import httpx

    models: list[dict[str, Any]] = []
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        for m in r.json().get("models", []):
            models.append({"model_id": m.get("name"), "source": "ollama"})
    except Exception as exc:
        models.append({"model_id": None, "source": "ollama",
                       "error": f"ollama unreachable: {exc}"})
    try:
        if HF_HUB_CACHE.is_dir():
            for child in sorted(HF_HUB_CACHE.iterdir()):
                if child.name.startswith("models--"):
                    models.append({"model_id": child.name[len("models--"):].replace("--", "/"),
                                   "source": "hf-cache"})
    except Exception as exc:
        models.append({"model_id": None, "source": "hf-cache", "error": str(exc)})
    return {"status": "completed", "models": models, "aliases": ALIAS_MAP}
