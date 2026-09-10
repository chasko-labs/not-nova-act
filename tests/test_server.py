"""Unit 8 validation: 7 tools registered; live serve + list + free call."""

import asyncio


def test_seven_tools_registered():
    from not_nova_act.server import mcp

    async def names():
        tools = await mcp.list_tools()
        return sorted(t.name for t in tools)

    found = asyncio.run(names())
    assert len(found) == 9, found
    assert "browser_take_screenshot_tool" in found, found
    assert "browser_assert_visual_tool" in found, found
    assert "browser_compress_shot_tool" in found, found


def _tool_schema(tool):
    """FastMCP Tool -> JSON input schema, across minor API shapes."""
    for attr in ("inputSchema", "input_schema", "parameters"):
        schema = getattr(tool, attr, None)
        if isinstance(schema, dict):
            return schema
    return {}


def _tool_by_name(name):
    from not_nova_act.server import mcp

    async def _find():
        for t in await mcp.list_tools():
            if t.name == name:
                return t
        return None

    return asyncio.run(_find())


def test_screenshot_tool_exposes_viewport_param():
    tool = _tool_by_name("browser_take_screenshot_tool")
    assert tool is not None
    props = _tool_schema(tool).get("properties", {})
    assert "viewport" in props, props
    # max_width stays a distinct output cap, not conflated with render width
    assert "max_width" in props, props


def test_check_page_tool_exposes_viewport_param():
    tool = _tool_by_name("browser_check_page_tool")
    assert tool is not None
    props = _tool_schema(tool).get("properties", {})
    assert "viewport" in props, props


def test_screenshot_wrapper_threads_viewport(monkeypatch):
    """The tool wrapper must forward viewport to browser_take_screenshot,
    not hardcode None (the original defect)."""
    import not_nova_act.server as srv

    captured = {}

    def fake_take(url, wait_seconds, full_page, viewport=None, max_width=None):
        captured.update(url=url, viewport=viewport, max_width=max_width)
        return {"status": "completed"}

    monkeypatch.setattr(srv, "browser_take_screenshot", fake_take)
    srv.browser_take_screenshot_tool(
        "https://example.com", viewport={"width": 375, "height": 812})
    assert captured["viewport"] == {"width": 375, "height": 812}, captured


def test_check_page_wrapper_threads_viewport(monkeypatch):
    import not_nova_act.server as srv

    captured = {}

    def fake_check(url, checks, viewport=None):
        captured.update(url=url, viewport=viewport)
        return {"status": "completed"}

    monkeypatch.setattr(srv, "browser_check_page", fake_check)
    srv.browser_check_page_tool(
        "https://example.com", [], viewport={"width": 768, "height": 1024})
    assert captured["viewport"] == {"width": 768, "height": 1024}, captured


def test_screenshot_wrapper_defaults_viewport_none(monkeypatch):
    import not_nova_act.server as srv

    captured = {}

    def fake_take(url, wait_seconds, full_page, viewport=None, max_width=None):
        captured.update(viewport=viewport)
        return {"status": "completed"}

    monkeypatch.setattr(srv, "browser_take_screenshot", fake_take)
    srv.browser_take_screenshot_tool("https://example.com")
    assert captured["viewport"] is None, captured
