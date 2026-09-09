"""Unit 6: pure-Python Workflow runner. Steps share one context dict;
model calls happen only inside act/act_get steps (units 3-4)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowStep:
    kind: str  # check | screenshot | assert | act | act_get
    task: str = ""
    url: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    schema: dict[str, str] | None = None
    max_steps: int = 6
    on_error: str = "fail"  # fail | continue


def _build_model(schema: dict[str, str]):
    from pydantic import create_model

    kinds = {"str": str, "int": int, "float": float, "bool": bool}
    return create_model("InlineSchema",
                        **{k: (kinds.get(v, str), ...) for k, v in schema.items()})


def run_workflow(defn: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
    """Sequential stepper over a def dict. Envelope return, never raises."""
    from .act import browser_act
    from .extract import browser_act_get
    from .hands import browser_check_page, browser_take_screenshot
    from .locks import get_valkey
    from .observe import log_step

    run_id = run_id or f"wf-{uuid.uuid4().hex[:8]}"
    client = get_valkey()
    context: dict[str, Any] = {"starting_page": defn.get("starting_page", "")}
    results: list[dict[str, Any]] = []
    started = time.time()
    try:
        for i, raw in enumerate(defn.get("steps", [])):
            step = WorkflowStep(**{k: v for k, v in raw.items()
                                   if k in WorkflowStep.__dataclass_fields__})
            url = step.url or context["starting_page"]
            if step.kind == "check":
                out = browser_check_page(url, step.checks)
            elif step.kind == "screenshot":
                out = browser_take_screenshot(url)
            elif step.kind == "assert":
                key, want = step.task.split("==", 1)
                got = str(context.get(key.strip(), ""))
                out = {"status": "completed" if got == want.strip() else "error",
                       "got": got, "want": want.strip()}
            elif step.kind == "act":
                out = browser_act(step.task, url, max_steps=step.max_steps,
                                  run_id=f"{run_id}-s{i}")
            elif step.kind == "act_get":
                model = _build_model(step.schema or {})
                out = browser_act_get(step.task, url, model,
                                      max_steps=step.max_steps,
                                      run_id=f"{run_id}-s{i}")
                if out.get("status") == "completed":
                    context.update(out.get("data", {}))
            else:
                out = {"status": "error", "error_message": f"unknown step {step.kind}"}
            entry = {"step": i, "kind": step.kind, "status": out.get("status")}
            results.append(entry)
            log_step(client, run_id, entry)
            if out.get("status") != "completed" and step.on_error == "fail":
                return {"status": "error", "run_id": run_id, "context": context,
                        "results": results, "failed_step": i,
                        "elapsed_seconds": round(time.time() - started, 1)}
        return {"status": "completed", "run_id": run_id, "context": context,
                "results": results,
                "elapsed_seconds": round(time.time() - started, 1)}
    except Exception as exc:
        return {"status": "error", "run_id": run_id, "context": context,
                "results": results, "error_message": str(exc)[:300]}


def load_def(path: str) -> dict[str, Any]:
    import yaml

    with open(path) as f:
        return yaml.safe_load(f)
