"""Unit 4: browser_act_get — terminal constrained decode, pydantic
validation, glimmer repair. Glimmer is CPU-slow: repair prompts stay tiny."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from pydantic import BaseModel

GLIMMER_URL = os.environ.get("GLIMMER_URL", "http://127.0.0.1:8181")
GLIMMER_MODEL = os.environ.get("NOT_NOVA_ACT_REPAIR_MODEL", "glimmer")


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


def _unload_planner(model: str) -> None:
    """Best-effort ollama unload so glimmer meets its VRAM floor.
    Qwen lazy-reloads on next use. Never raises."""
    import httpx

    from .planner import OLLAMA_URL

    try:
        httpx.post(f"{OLLAMA_URL}/api/generate",
                   json={"model": model, "keep_alive": 0, "stream": False},
                   timeout=30)
    except Exception:
        pass


def qwen_repair(raw: str, schema: type[BaseModel],
                timeout: int = 280) -> BaseModel:
    """Second-pass coercion via the planner model (fast, local GPU).
    Raises on failure."""
    import httpx

    from .planner import OLLAMA_URL, PLANNER_MODEL

    prompt = ("Fix this into valid JSON matching the schema "
              f"{json.dumps(schema.model_json_schema())}. "
              "Output ONLY the fixed JSON object, no prose.\n"
              f"BROKEN:\n{raw[:2000]}")
    body = {"model": PLANNER_MODEL, "prompt": prompt,
            "stream": False, "options": {"num_ctx": 4096, "think": False}}
    r = httpx.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=timeout)
    r.raise_for_status()
    return schema.model_validate_json(_extract_json(r.json().get("response", "")))


def glimmer_repair(raw: str, schema: type[BaseModel],
                   timeout: int = 420, max_tokens: int = 150) -> BaseModel:
    """Coerce malformed extractor output via glimmer. Raises on failure."""
    import httpx

    from .planner import PLANNER_MODEL

    _unload_planner(PLANNER_MODEL)
    prompt = ("Fix this into valid JSON matching the schema "
              f"{json.dumps(schema.model_json_schema())}. "
              "Output ONLY the fixed JSON, no prose.\n"
              f"BROKEN:\n{raw[:2000]}")
    body = {"model": GLIMMER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "stream": False}
    r = httpx.post(f"{GLIMMER_URL}/v1/chat/completions", json=body, timeout=timeout)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    text = (msg.get("content") or msg.get("reasoning_content") or "")
    return schema.model_validate_json(_extract_json(text))


def extract_structured(task: str, obs: dict[str, Any], schema: type[BaseModel],
                       model_timeout: int = 280, dom_text: str = "") -> BaseModel:
    """Qwen terminal decode + validate. Raises on transport/parse failure.
    dom_text is the deterministic signal (perceive order: DOM before vision)."""
    import httpx

    from .planner import _prompt, _shrink_for_planning, PLANNER_MODEL, OLLAMA_URL

    lines = [
        "You are a data extractor. Output ONE JSON object only, no prose,",
        "no action fields, no commentary.",
        f"Task: {task}",
        f"JSON schema: {json.dumps(schema.model_json_schema())}",
    ]
    if dom_text:
        lines.append("Page text (authoritative, transcribe from here first):")
        lines.append(dom_text[:2000])
    else:
        lines.append("No page text available; read the screenshot.")
        for c in obs.get("candidates", []):
            lines.append(f'  {c["ref"]}: {c["role"]} name="{c["name"]}"')
    lines.append("Reply with the JSON object only.")
    prompt = "\n".join(lines)
    body = {"model": PLANNER_MODEL, "prompt": prompt,
            "images": [_shrink_for_planning(obs["screenshot_png"])],
            "stream": False, "options": {"num_ctx": 8192, "think": False}}
    r = httpx.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=model_timeout)
    r.raise_for_status()
    return schema.model_validate_json(_extract_json(r.json().get("response", "")))


def browser_act_get(task: str, starting_page: str, schema: type[BaseModel],
                    max_steps: int = 6, timeout_seconds: int = 420,
                    run_id: str | None = None) -> dict[str, Any]:
    """Navigate (planner-driven, ≤3 steps), then extract + validate + repair.
    Envelope return, never raises."""
    import uuid

    from playwright.sync_api import sync_playwright

    from .act import _dispatch
    from .hands import DEFAULT_VIEWPORT
    from .locks import Semaphore, acquire_gpu_lock, get_valkey, release_gpu_lock
    from .observe import log_step, observe_snapshot
    from .planner import plan_action

    run_id = run_id or f"get-{uuid.uuid4().hex[:8]}"
    client = get_valkey()
    deadline = time.time() + timeout_seconds
    if not Semaphore(client).acquire():
        return {"status": "rate_limited", "run_id": run_id}
    token = acquire_gpu_lock(client)
    steps: list[dict[str, Any]] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport=DEFAULT_VIEWPORT)
            page.goto(starting_page, wait_until="networkidle", timeout=60000)
            for step in range(min(max_steps, 3)):
                if time.time() > deadline:
                    break
                obs = observe_snapshot(page)
                try:
                    plan = plan_action(task, obs)
                except Exception as exc:
                    steps.append({"step": step, "status": "plan_error",
                                  "error": str(exc)[:300]})
                    continue
                result = _dispatch(page, plan, obs["candidates"])
                steps.append({"step": step, "action": plan.action, "ok": result["ok"]})
                if plan.action == "done" and result["ok"]:
                    break
            obs = observe_snapshot(page)
            try:
                dom_text = page.locator("body").inner_text()[:2000]
            except Exception:
                dom_text = ""
            browser.close()
        try:
            parsed = extract_structured(task, obs, schema, dom_text=dom_text)
            return {"status": "completed", "run_id": run_id, "steps": steps,
                    "data": parsed.model_dump()}
        except Exception as first_exc:
            raw = str(first_exc)[:2000]
        finally:
            release_gpu_lock(client, token)
            token = None
        # repair chain: fast local retry first, shared glimmer second.
        # glimmer on this host is CPU-slow and idle-reaped; its failure is
        # recorded, not fatal.
        repair_notes: list[str] = []
        for repair_fn in (qwen_repair, glimmer_repair):
            try:
                repaired = repair_fn(raw, schema)
                return {"status": "completed", "run_id": run_id, "steps": steps,
                        "data": repaired.model_dump(), "repaired": True,
                        "repair_notes": repair_notes}
            except Exception as exc:
                repair_notes.append(f"{repair_fn.__name__}: {str(exc)[:150]}")
        return {"status": "error", "run_id": run_id, "steps": steps,
                "error_message": f"extract failed: {'; '.join(repair_notes)[:300]}"}
    except Exception as exc:
        return {"status": "error", "run_id": run_id, "steps": steps,
                "error_message": str(exc)[:300]}
    finally:
        release_gpu_lock(client, token)
