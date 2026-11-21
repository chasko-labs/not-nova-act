"""Planner: observation -> strict JSON action. Prompt-level JSON discipline
(the ollama format:json flag returned empty in smoke testing).

Backend is Bedrock Nova Lite via the Converse API (local inference is not
used). NOT_NOVA_ACT_PLANNER_BACKEND=ollama keeps the legacy ollama path."""

from __future__ import annotations

import base64
import json
import os
import subprocess
from typing import Any, Literal

from pydantic import BaseModel, Field

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
PLANNER_MODEL = os.environ.get("NOT_NOVA_ACT_PLANNER_MODEL", "qwen3-vl:8b")
PLANNER_BACKEND = os.environ.get("NOT_NOVA_ACT_PLANNER_BACKEND", "bedrock")
BEDROCK_REGION = os.environ.get("NOT_NOVA_ACT_BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL = os.environ.get(
    "NOT_NOVA_ACT_BEDROCK_MODEL", "amazon.nova-lite-v1:0")
# Planner JSON is tiny; an explicit cap keeps quota reservation small.
BEDROCK_MAX_TOKENS = int(os.environ.get(
    "NOT_NOVA_ACT_BEDROCK_MAX_TOKENS", "512"))


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
    a11y = str(obs.get("a11y", ""))[:1500]
    if a11y:
        lines.append("Accessibility tree (structure reference):")
        lines.append(a11y)
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


def _plan_bedrock(prompt: str, jpeg_b64: str, timeout: int) -> ActionPlan:
    """One Converse call with the screenshot. Raises -> caller retries."""
    messages = [{"role": "user", "content": [
        {"text": prompt},
        {"image": {"format": "jpeg", "source": {
            "bytes": jpeg_b64}}},
    ]}]
    # NOTE: no --cli-binary-format flag — inline base64 image bytes in
    # --messages parse as-is; the flag breaks blob input (CLI exit 254).
    cmd = ["aws", "bedrock-runtime", "converse",
           "--region", BEDROCK_REGION,
           "--model-id", BEDROCK_MODEL,
           "--messages", json.dumps(messages),
           "--inference-config",
           json.dumps({"maxTokens": BEDROCK_MAX_TOKENS})]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=max(10, timeout))
    out.check_returncode()
    blocks = json.loads(out.stdout)["output"]["message"]["content"]
    text = "".join(b.get("text", "") for b in blocks)
    return ActionPlan.model_validate_json(_extract_json(text))


def _coerce_plan(text: str) -> ActionPlan:
    """Parse one ActionPlan, tolerating small-model shape drift.

    Small local planners (minicpm-v) sometimes emit a single-element
    list of action dicts instead of the bare object. Coerce
    deterministically — no model call.
    """
    try:
        return ActionPlan.model_validate_json(_extract_json(text))
    except Exception:
        pass
    data = json.loads(_extract_json(text))
    if isinstance(data, list):
        for item in data:
            try:
                return ActionPlan.model_validate(item)
            except Exception:
                continue
    return ActionPlan.model_validate_json(_extract_json(text))


def plan_action(task: str, obs: dict[str, Any],
                model: str = PLANNER_MODEL, timeout: int = 280) -> ActionPlan:
    """One planner call. Raises on transport/parse failure (caller retries)."""
    import httpx

    shot_b64 = _shrink_for_planning(obs["screenshot_png"])
    if PLANNER_BACKEND == "bedrock":
        return _plan_bedrock(_prompt(task, obs), shot_b64, timeout)
    body = {"model": model, "prompt": _prompt(task, obs),
            "images": [shot_b64], "stream": False,
            "options": {"num_ctx": 4096, "think": False}}
    r = httpx.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=timeout)
    r.raise_for_status()
    text = r.json().get("response", "")
    try:
        return _coerce_plan(text)
    except Exception:
        repair = body | {"prompt": (
            "Rewrite as ONE JSON object only, no list, no prose: "
            '{"action": "click|fill|select|scroll|goto|wait|done", '
            '"target_ref": "cN", "text": "value", "confidence": 0.0-1.0}. '
            f"Fix this output:\n{text[:2000]}")}
        r2 = httpx.post(f"{OLLAMA_URL}/api/generate", json=repair,
                        timeout=timeout)
        r2.raise_for_status()
        return _coerce_plan(r2.json().get("response", ""))
