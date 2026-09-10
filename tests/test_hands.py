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
