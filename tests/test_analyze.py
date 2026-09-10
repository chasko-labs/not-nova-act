"""Compression ratio + live local-model visual verdict (no agent vision)."""

from not_nova_act import browser_take_screenshot
from not_nova_act.analyze import assert_visual
from not_nova_act.hands import compress_image


def test_compress_shrinks_rich_png():
    # flat pages (example.com: 19KB PNG -> 25KB JPEG) do NOT benefit;
    # rich pages do (sumerian: 494KB -> 97KB). test the paying case.
    res = browser_take_screenshot("https://bryanchasko.com/sumerian-squares/",
                                  wait_seconds=1)
    assert res["status"] == "completed", res
    out = compress_image(res["screenshot_path"])
    assert out["status"] == "completed", out
    assert out["bytes"] < out["source_bytes"] // 2, out


def test_assert_visual_true_and_false():
    res = browser_take_screenshot("https://example.com", wait_seconds=1,
                                  max_width=800)
    assert res["status"] == "completed", res
    yes = assert_visual(res["screenshot_path"],
                        "the page shows the heading Example Domain")
    assert yes["status"] == "completed", yes
    assert yes["verdict"] is True, yes
    no = assert_visual(res["screenshot_path"],
                       "the page shows a red Begin button")
    assert no["status"] == "completed", no
    assert no["verdict"] is False, no
