"""Qwen3-vl planner: observation -> strict JSON action. Prompt-level JSON
discipline (the ollama format:json flag returned empty in smoke testing)."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
PLANNER_MODEL = os.environ.get("NOT_NOVA_ACT_PLANNER_MODEL", "qwen3-vl:8b")


class ActionPlan(BaseModel):
    action: Literal["click", "fill", "select", "scroll", "goto", "wait", "done"]
    target_ref: str = ""
    text: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def _prompt(task: str, obs: dict[str, Any]) -> str:
    lines = [
        "You are a browser operator. Output ONE JSON object only, no prose:",
        '{"action": "click|fill|select|scroll|goto|wait|done", '
        '"target_ref": "cN", "text": "value for fill/select/goto", '
        '"confidence": 0.0-1.0}',
        f"User task: {task}",
        "Candidates:",
    ]
    for c in obs.get("candidates", []):
        lines.append(f'  {c["ref"]}: {c["role"]} name="{c["name"]}" box={c["box"]}')
    lines.append("Reply with the JSON object only.")
    return "\n".join(lines)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start:end + 1]
    return text


PLAN_IMAGE_WIDTH = 768


def _shrink_for_planning(png_bytes: bytes) -> str:
    """Downscale to JPEG for fast prefill on partial GPU offload. Full-res
    screenshots stay in artifacts; planning never needs them."""
    import base64
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if im.width > PLAN_IMAGE_WIDTH:
        im = im.resize((PLAN_IMAGE_WIDTH, int(im.height * PLAN_IMAGE_WIDTH / im.width)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def plan_action(task: str, obs: dict[str, Any],
                model: str = PLANNER_MODEL, timeout: int = 280) -> ActionPlan:
    """One planner call. Raises on transport/parse failure (caller retries)."""
    import httpx

    shot_b64 = _shrink_for_planning(obs["screenshot_png"])
    body = {"model": model, "prompt": _prompt(task, obs),
            "images": [shot_b64], "stream": False,
            "options": {"num_ctx": 8192, "think": False}}
    r = httpx.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=timeout)
    r.raise_for_status()
    text = r.json().get("response", "")
    return ActionPlan.model_validate_json(_extract_json(text))
