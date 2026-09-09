"""Unit 3: browser_act loop — observe → plan → dispatch → verify → log."""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import sync_playwright

from .hands import DEFAULT_VIEWPORT
from .locks import Semaphore, acquire_gpu_lock, get_valkey, release_gpu_lock
from .observe import log_step, observe_snapshot
from .planner import plan_action


def _dispatch(page, plan, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    target = next((c for c in candidates if c["ref"] == plan.target_ref), None)
    try:
        if plan.action == "done":
            return {"ok": True, "detail": "planner signaled done"}
        if plan.action == "goto":
            page.goto(plan.text, wait_until="networkidle", timeout=60000)
            return {"ok": True, "detail": f"navigated {plan.text}"}
        if plan.action == "wait":
            page.wait_for_timeout(2000)
            return {"ok": True, "detail": "waited"}
        if target is None:
            return {"ok": False, "detail": f"unknown ref {plan.target_ref}"}
        loc = page.get_by_role(target["role"], name=target["name"]).first
        if plan.action == "click":
            loc.click(timeout=10000)
            return {"ok": True, "detail": f"clicked {plan.target_ref}"}
        if plan.action == "fill":
            loc.fill(plan.text, timeout=10000)
            return {"ok": True, "detail": f"filled {plan.target_ref}"}
        if plan.action == "select":
            loc.select_option(plan.text, timeout=10000)
            return {"ok": True, "detail": f"selected {plan.target_ref}"}
        if plan.action == "scroll":
            loc.scroll_into_view_if_needed(timeout=10000)
            return {"ok": True, "detail": f"scrolled {plan.target_ref}"}
        return {"ok": False, "detail": f"unsupported action {plan.action}"}
    except Exception as exc:
        return {"ok": False, "detail": f"dispatch raised: {exc}"}


def browser_act(task: str, starting_page: str, max_steps: int = 10,
                timeout_seconds: int = 300, run_id: str | None = None) -> dict[str, Any]:
    """One NL task, bounded loop. Envelope return, never raises."""
    import uuid

    run_id = run_id or f"act-{uuid.uuid4().hex[:8]}"
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
            before = page.screenshot(full_page=False)
            for step in range(max_steps):
                if time.time() > deadline:
                    steps.append({"step": step, "status": "timeout"})
                    break
                obs = observe_snapshot(page)
                try:
                    plan = plan_action(task, obs)
                except Exception as exc:
                    steps.append({"step": step, "status": "plan_error",
                                  "error": str(exc)[:300]})
                    continue
                candidates = obs["candidates"]
                target = next((c for c in candidates
                               if c["ref"] == plan.target_ref), None)
                dupes = (sum(1 for c in candidates
                             if target and c["name"] == target["name"]) > 1
                         if target else False)
                if plan.action in ("click", "fill", "select", "scroll") and (
                        plan.confidence < 0.5 or dupes):
                    from .rerank import rerank_candidates

                    ranked = rerank_candidates(plan.text or task,
                                               obs["screenshot_png"], candidates)
                    if ranked:
                        plan = plan.model_copy(
                            update={"target_ref": ranked[0]["ref"]})
                result = _dispatch(page, plan, candidates)
                entry = {"step": step, "action": plan.action,
                         "target_ref": plan.target_ref,
                         "confidence": plan.confidence, "ok": result["ok"],
                         "detail": result["detail"][:300]}
                steps.append(entry)
                log_step(client, run_id, entry)
                if plan.action == "done" and result["ok"]:
                    break
            after = page.screenshot(full_page=False)
            browser.close()
        completed = any(s.get("ok") for s in steps)
        return {"status": "completed" if completed else "error", "run_id": run_id,
                "steps": steps, "steps_completed": len(steps),
                "page_changed": before != after}
    except Exception as exc:
        return {"status": "error", "run_id": run_id, "error_message": str(exc),
                "steps": steps}
    finally:
        release_gpu_lock(client, token)
