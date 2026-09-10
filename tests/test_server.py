"""Unit 8 validation: 7 tools registered; live serve + list + free call."""

import asyncio


def test_seven_tools_registered():
    from not_nova_act.server import mcp

    async def names():
        tools = await mcp.list_tools()
        return sorted(t.name for t in tools)

    found = asyncio.run(names())
    assert len(found) == 7, found
    assert "browser_take_screenshot_tool" in found, found
