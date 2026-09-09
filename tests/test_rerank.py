"""Unit 5 validation: duplicate-name fixture resolves to the red button."""

from playwright.sync_api import sync_playwright

from not_nova_act.observe import observe_snapshot
from not_nova_act.rerank import rerank_candidates

PAGE = (
    "data:text/html,"
    "<style>body{font-family:sans-serif;background:white}"
    "button{font-size:30px;margin:20px;padding:10px 20px;color:white;border:none}"
    ".r{background:red}.b{background:blue}</style>"
    "<button class='b'>Launch</button><button class='r'>Launch</button>"
)


def test_rerank_prefers_red_launch():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(PAGE)
        obs = observe_snapshot(page)
        browser.close()
    launches = [c for c in obs["candidates"] if c["name"] == "Launch"]
    assert len(launches) == 2, [c["name"] for c in obs["candidates"]]
    ranked = rerank_candidates("the red Launch button",
                               obs["screenshot_png"], launches)
    assert len(ranked) == 2
    assert ranked[0]["clip_score"] > ranked[1]["clip_score"]
    # red button is second in DOM order; it must rank first
    assert ranked[0]["box"]["x"] > ranked[1]["box"]["x"], ranked
