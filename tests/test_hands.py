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
