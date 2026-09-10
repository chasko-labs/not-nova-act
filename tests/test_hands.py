"""Unit 1 validation: real browser, real assertions. Mirrors the plan's
Unit 1 evidence row: screenshot PNG exists, heading assert passes,
registry names qwen3-vl:8b."""

import os
from pathlib import Path

from not_nova_act import browser_check_page, browser_list_models, browser_take_screenshot


def test_take_screenshot_returns_existing_png():
    res = browser_take_screenshot("https://example.com", wait_seconds=1)
    assert res["status"] == "completed", res
    assert Path(res["screenshot_path"]).stat().st_size > 0
    assert res["page_title"] == "Example Domain"
    assert res["final_url"].startswith("https://example.com")


def test_check_page_asserts_heading():
    res = browser_check_page("https://example.com", [
        {"type": "text_contains", "selector": "h1", "expected": "Example Domain",
         "description": "h1 names the domain"},
        {"type": "visible", "selector": "a", "description": "link visible"},
        {"type": "evaluate", "expression": "document.title",
         "description": "title readable"},
    ], wait_seconds=1)
    assert res["status"] == "completed", res
    assert res["all_passed"], res["results"]


def test_list_models_names_qwen():
    res = browser_list_models()
    assert res["status"] == "completed", res
    ids = [m.get("model_id") for m in res["models"]]
    assert "qwen3-vl:8b" in ids, ids
    assert res["aliases"]["latest-vision"] == "qwen3-vl:8b"


def test_error_envelope_never_raises():
    res = browser_take_screenshot("http://127.0.0.1:9/nonexistent", wait_seconds=0)
    assert res["status"] == "error"
    assert "error_message" in res


def test_max_width_caps_reader_size():
    from PIL import Image

    res = browser_take_screenshot("https://example.com", wait_seconds=1,
                                  max_width=800)
    assert res["status"] == "completed", res
    with Image.open(res["screenshot_path"]) as im:
        assert im.size[0] <= 800, im.size
    assert res["image_size"]["width"] <= 800


def test_screenshot_honors_requested_viewport():
    res = browser_take_screenshot("https://example.com", wait_seconds=1,
                                  viewport={"width": 375, "height": 812})
    assert res["status"] == "completed", res
    assert res["viewport"] == {"width": 375, "height": 812}, res


def test_screenshot_defaults_to_1280_when_viewport_omitted():
    res = browser_take_screenshot("https://example.com", wait_seconds=1)
    assert res["status"] == "completed", res
    assert res["viewport"] == {"width": 1280, "height": 800}, res


def test_check_page_honors_requested_viewport():
    res = browser_check_page("https://example.com", [
        {"type": "evaluate", "expression": "window.innerWidth", "expected": 375,
         "description": "innerWidth reflects requested mobile viewport"},
    ], wait_seconds=1, viewport={"width": 375, "height": 812})
    assert res["status"] == "completed", res
    assert res["all_passed"], res["results"]


def test_check_page_defaults_to_1280_when_viewport_omitted():
    res = browser_check_page("https://example.com", [
        {"type": "evaluate", "expression": "window.innerWidth", "expected": 1280,
         "description": "innerWidth defaults to 1280 when viewport omitted"},
    ], wait_seconds=1)
    assert res["status"] == "completed", res
    assert res["all_passed"], res["results"]


# Self-contained WebGL page: clear to solid red, no network/live-game dependency.
# gl.readPixels center-sample is the exact probe that proved the canvas blank
# ([0,0,0,0] for all samples). preserveDrawingBuffer:true keeps the buffer
# readable after compositing so the readback is deterministic (the default
# discards it, which is what made a still-frame sample read transparent).
_WEBGL_PAGE = (
    "data:text/html,"
    "<canvas id=c width=256 height=256></canvas>"
    "<script>"
    "var gl=document.getElementById('c').getContext("
    "'webgl',{preserveDrawingBuffer:true});"
    "gl.clearColor(1,0,0,1);"
    "gl.clear(gl.COLOR_BUFFER_BIT);"
    "gl.finish();"
    "window.__probe=function(){"
    "var p=new Uint8Array(4);"
    "gl.readPixels(128,128,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);"
    "return [p[0],p[1],p[2],p[3]];"
    "};"
    "</script>"
)


def test_webgl_canvas_paints_non_transparent_pixels():
    """Regression guard for the blank-canvas bug: headless chromium must paint
    WebGL to a readable framebuffer. Mirrors the gl.readPixels center-sample
    that proved the live canvas blank ([0,0,0,0]). With the pinned
    SwiftShader-via-ANGLE path and preserveDrawingBuffer the center reads solid
    red [255,0,0,255]."""
    res = browser_check_page(_WEBGL_PAGE, [
        {"type": "evaluate", "expression": "!!window.WebGLRenderingContext",
         "expected": True, "description": "webgl available"},
        {"type": "evaluate", "expression": "window.__probe()[3] > 0",
         "expected": True, "description": "center pixel alpha nonzero (painted)"},
        {"type": "evaluate", "expression": "window.__probe()[0] > 0",
         "expected": True, "description": "center pixel red channel nonzero"},
    ], wait_seconds=2)
    assert res["status"] == "completed", res
    assert res["all_passed"], res["results"]


# Self-contained responsive page: a viewport meta tag (width=device-width) plus
# a (max-width:480px) rule that shrinks #box from 800px to 100px. The ONLY thing
# that decides which rule wins is what device-width resolves to. On a plain
# 375-window (no is_mobile) device-width = the ~1280 screen, the desktop rule
# wins, #box stays 800. With mobile emulation device-width = 375, the media
# query matches and #box becomes 100. This is the exact desktop-vs-mobile fork
# the "375 window measured at desktop x" bug lived in.
# NOTE: the id selectors are written %23box (percent-encoded #) on purpose -- a
# literal # in a data: URL starts the fragment and truncates the document before
# the style block loads, leaving getElementById('box') null. do not "fix" %23 to #.
_RESPONSIVE_PAGE = (
    "data:text/html,"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<style>"
    "%23box{width:800px}"
    "@media (max-width:480px){%23box{width:100px}}"
    "</style>"
    "<div id=box>x</div>"
)


def test_mobile_emulation_makes_device_width_track_viewport():
    """Proves the fix: with mobile=True a 375 viewport sets CDP device metrics
    so `width=device-width` resolves to 375, matchMedia('(max-width:480px)')
    matches, clientWidth is 375, and the mobile @media rule wins (#box 100px)."""
    res = browser_check_page(_RESPONSIVE_PAGE, [
        {"type": "evaluate",
         "expression": "matchMedia('(max-width:480px)').matches",
         "expected": True,
         "description": "max-width:480 media query matches on emulated device"},
        {"type": "evaluate",
         "expression": "document.documentElement.clientWidth",
         "expected": 375,
         "description": "device-width tracks emulated viewport, not screen"},
        {"type": "evaluate",
         "expression": "Math.round(document.getElementById('box').getBoundingClientRect().width)",
         "expected": 100,
         "description": "mobile @media rule wins (#box 100px, not desktop 800)"},
    ], wait_seconds=1, viewport={"width": 375, "height": 812}, mobile=True)
    assert res["status"] == "completed", res
    assert res["mobile"] is True, res
    assert res["all_passed"], res["results"]


def test_desktop_1280_does_not_match_mobile_media_query():
    """Contrast case: at desktop 1280 (mobile omitted) the (max-width:480px)
    rule must NOT match and #box keeps its desktop 800px width. Guards against
    the mobile-emulation path leaking into default desktop captures."""
    res = browser_check_page(_RESPONSIVE_PAGE, [
        {"type": "evaluate",
         "expression": "matchMedia('(max-width:480px)').matches",
         "expected": False,
         "description": "max-width:480 media query does NOT match at 1280"},
        {"type": "evaluate",
         "expression": "document.documentElement.clientWidth > 480",
         "expected": True,
         "description": "device-width is the desktop width, not a mobile one"},
        {"type": "evaluate",
         "expression": "Math.round(document.getElementById('box').getBoundingClientRect().width)",
         "expected": 800,
         "description": "desktop rule wins (#box 800px)"},
    ], wait_seconds=1)
    assert res["status"] == "completed", res
    assert res["mobile"] is False, res
    assert res["all_passed"], res["results"]
