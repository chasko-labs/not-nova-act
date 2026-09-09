"""Unit 2 validation: observe output shape + valkey stream round-trip."""

import uuid

from playwright.sync_api import sync_playwright

from not_nova_act.observe import get_valkey, log_step, observe_snapshot, read_steps


def test_observe_has_shot_a11y_boxes():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto("https://example.com", wait_until="networkidle", timeout=60000)
        obs = observe_snapshot(page)
        browser.close()
    assert isinstance(obs["screenshot_png"], bytes) and len(obs["screenshot_png"]) > 0
    assert isinstance(obs["a11y"], dict)
    assert len(obs["candidates"]) > 0, "example.com has a link; expect candidates"
    assert all(set(c) == {"ref", "role", "name", "box"} for c in obs["candidates"])
    assert len(obs["candidates"]) <= 30


def test_step_log_round_trip():
    client = get_valkey()
    run_id = f"test-{uuid.uuid4().hex[:8]}"
    assert log_step(client, run_id, {"step": 0, "action": "goto", "ok": True})
    entries = read_steps(client, run_id)
    assert len(entries) == 1
    client.delete(f"not-nova-act:run:{run_id}")
