"""Unit 2: observe (screenshot + a11y + boxes) + valkey step log."""

from __future__ import annotations

import os
from typing import Any

VALKEY_HOST = os.environ.get("NOT_NOVA_ACT_VALKEY_HOST", "127.0.0.1")
VALKEY_PORT = int(os.environ.get("NOT_NOVA_ACT_VALKEY_PORT", "16379"))
STREAM_PREFIX = "not-nova-act:run:"
MAX_CANDIDATES = 30

INTERACTIVE_ROLES = (
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "switch", "slider", "spinbutton", "menuitem", "tab",
)


def observe_snapshot(page, max_candidates: int = MAX_CANDIDATES) -> dict[str, Any]:
    """Cheapest-signals-first observation. No model. Returns dict with
    screenshot_png bytes, a11y snapshot, and refined candidate boxes."""
    shot = page.screenshot(full_page=False)
    try:
        a11y = page.accessibility.snapshot() or {}
    except Exception:
        a11y = {}
    candidates: list[dict[str, Any]] = []
    for role in INTERACTIVE_ROLES:
        if len(candidates) >= max_candidates:
            break
        try:
            locators = page.get_by_role(role).all()
        except Exception:
            continue
        for loc in locators:
            if len(candidates) >= max_candidates:
                break
            try:
                if not loc.is_visible():
                    continue
                box = loc.bounding_box()
                if not box:
                    continue
                name = (loc.get_attribute("aria-label") or loc.inner_text() or "")[:120]
                candidates.append({
                    "ref": f"c{len(candidates)}",
                    "role": role,
                    "name": name.strip(),
                    "box": {k: round(v) for k, v in box.items()},
                })
            except Exception:
                continue
    return {"screenshot_png": shot, "a11y": a11y, "candidates": candidates}


def get_valkey():
    import redis

    return redis.Redis(host=VALKEY_HOST, port=VALKEY_PORT, socket_timeout=5)


def log_step(client, run_id: str, entry: dict[str, Any]) -> bool:
    """Append a step entry to the run stream. Fail-open: False, never raises."""
    try:
        # redis-py encoder rejects bool (even though bool subclasses int),
        # so normalize bools to ints and stringify everything else.
        def enc(v):
            if isinstance(v, bool):
                return int(v)
            if isinstance(v, (str, bytes, int, float)):
                return v
            return repr(v)[:2000]

        flat = {k: enc(v) for k, v in entry.items()}
        client.xadd(f"{STREAM_PREFIX}{run_id}", flat)
        return True
    except Exception:
        return False


def read_steps(client, run_id: str) -> list[dict[str, Any]]:
    try:
        return [dict(fields) for _, fields in
                client.xrange(f"{STREAM_PREFIX}{run_id}")]
    except Exception:
        return []
