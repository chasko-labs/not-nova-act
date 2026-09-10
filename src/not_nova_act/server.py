"""Unit 8: FastMCP streamable-http server exposing the 7 local tools.
Envelopes {completed|rate_limited|timeout|error}; never raises to caller."""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from not_nova_act.act import browser_act
from not_nova_act.extract import browser_act_get
from not_nova_act.hands import (
    browser_check_page,
    browser_list_models,
    browser_take_screenshot,
)
from not_nova_act.workflow import load_def, run_workflow

PORT = int(os.environ.get("NOT_NOVA_ACT_PORT", "8171"))
HOST = os.environ.get("NOT_NOVA_ACT_HOST", "127.0.0.1")

mcp = FastMCP(
    name="not-nova-act",
    instructions=(
        "Local-first browser-use. browser_take_screenshot, browser_check_page, "
        "and browser_list_models are free (no model). browser_act and "
        "browser_act_get spend local qwen3-vl time; browser_workflow runs "
        "YAML/JSON defs. browser_session opens a named starting point."
    ),
)


@mcp.tool()
def browser_session(starting_page: str, viewport: dict[str, int] | None = None) -> dict[str, Any]:
    """Open/navigate a session starting point; returns viewport fixture."""
    from not_nova_act.hands import DEFAULT_VIEWPORT

    return {"status": "completed", "starting_page": starting_page,
            "viewport": viewport or DEFAULT_VIEWPORT}


@mcp.tool()
def browser_act_tool(task: str, starting_page: str, max_steps: int = 10,
                     timeout_seconds: int = 300) -> dict[str, Any]:
    """One NL action step loop (plan+dispatch+verify). Model cost: qwen."""
    return browser_act(task, starting_page, max_steps, timeout_seconds)


@mcp.tool()
def browser_act_get_tool(task: str, starting_page: str,
                         schema: dict[str, str] | None = None,
                         max_steps: int = 6) -> dict[str, Any]:
    """NL extract to schema-constrained JSON. Model cost: qwen (+repair)."""
    from not_nova_act.workflow import _build_model

    try:
        model = _build_model(schema or {"text": "str"})
        return browser_act_get(task, starting_page, model, max_steps)
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:300]}


@mcp.tool()
def browser_workflow_tool(definition_path: str) -> dict[str, Any]:
    """Run a Workflow YAML/JSON def file. Cost: per contained step."""
    try:
        return run_workflow(load_def(definition_path))
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)[:300]}


@mcp.tool()
def browser_take_screenshot_tool(url: str, full_page: bool = True,
                                 wait_seconds: int = 3,
                                 max_width: int | None = None) -> dict[str, Any]:
    """Navigate + capture. Free (Playwright only). Pass max_width (e.g. 1280)
    when you intend to attach the PNG to a vision context (readers cap ~2000px)."""
    return browser_take_screenshot(url, wait_seconds, full_page,
                                   viewport=None, max_width=max_width)


@mcp.tool()
def browser_check_page_tool(url: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic DOM assertions. Free (no model)."""
    return browser_check_page(url, checks)


@mcp.tool()
def browser_list_models_tool() -> dict[str, Any]:
    """Local registry: ollama + HF cache + aliases. Free."""
    return browser_list_models()


def main() -> None:
    mcp.run(transport="streamable-http", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
