"""Local-model image analysis: qwen3-vl verdicts over screenshots, so
expensive agent vision (kiro/muse-spark) stays out of the loop. The model
reads the compressed sibling when present, else the source PNG."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from .hands import compress_image


def _payload(png_bytes: bytes) -> str:
    from PIL import Image

    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if im.width > 768:
        im = im.resize((768, int(im.height * 768 / im.width)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def describe_screenshot(screenshot_path: str, prompt: str,
                        timeout: int = 280) -> dict[str, Any]:
    """Free-form local VQA. Returns completed + text, never raises."""
    import httpx

    from .planner import OLLAMA_URL, PLANNER_MODEL

    try:
        raw = Path(screenshot_path).read_bytes()
        body = {"model": PLANNER_MODEL, "prompt": prompt,
                "images": [_payload(raw)], "stream": False,
                "options": {"num_ctx": 8192, "think": False}}
        r = httpx.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=timeout)
        r.raise_for_status()
        return {"status": "completed",
                "description": r.json().get("response", "").strip()[:2000]}
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:300]}


def assert_visual(screenshot_path: str, statement: str,
                  timeout: int = 280) -> dict[str, Any]:
    """Local true/false verdict on a visual claim, e.g. 'the Begin button
    is fully visible'. Returns completed + verdict, never raises."""
    out = describe_screenshot(
        screenshot_path,
        "Answer with exactly one word, TRUE or FALSE, then a short reason. "
        f"Claim: {statement}", timeout)
    if out["status"] != "completed":
        return out
    first = (out["description"].split() or [""])[0].upper()
    return {"status": "completed", "verdict": first == "TRUE",
            "detail": out["description"][:500]}


def compress_for_context(screenshot_path: str) -> dict[str, Any]:
    """One-step: compressed JPEG sibling for vision contexts."""
    return compress_image(Path(screenshot_path))
