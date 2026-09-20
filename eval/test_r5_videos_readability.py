"""R5 readability: favorite-typescript-videos module sections vs the
bryanchasko design system (dark theme, cards component, scannable type).

Two lenses: DOM metrics (deterministic) and a local vision review
(qwen3-vl:8b, no hosted calls). Both run against the LIVE page so the
score tracks what readers actually get.
"""

import base64
import re

import requests

URL = "https://bryanchasko.com/favorite-typescript-videos/"
MODULE_ANCHOR = "#module-04--functions-and-generics"
OLLAMA_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen3-vl:8b"

# Design bar, grounded in the shared system (dark surface, carded content,
# one idea per block). Entry prose above this reads as a wall.
MAX_WORDS_PER_ENTRY_PARAGRAPH = 120


def _module_shot(page, path):
    page.goto(URL, wait_until="networkidle")
    h2 = page.locator("h2#module-04--functions-and-generics")
    h2.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    from PIL import Image
    # tall viewport so the whole module fits one capture (full-page stitch
    # times out on this very long page)
    w = page.viewport_size["width"]
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(800)
    top = page.evaluate(
        "document.querySelector('h2#module-04--functions-and-generics')"
        ".getBoundingClientRect().top + window.scrollY")
    bot = page.evaluate(
        "document.querySelector('h2#module-05--objects-and-interfaces')"
        ".getBoundingClientRect().top + window.scrollY")
    need = int(bot - top + 40)
    page.set_viewport_size({"width": w, "height": min(max(need, 2000), 12000)})
    page.evaluate(f"window.scrollTo(0, {int(max(0, top - 20))})")
    page.wait_for_timeout(500)
    page.screenshot(path=path + ".tall.png")
    img = Image.open(path + ".tall.png")
    crop = img.crop((0, 0, w, int(min(img.height, need))))
    if crop.height > 3000:  # keep the vision call tractable, artifact stays sharp
        crop = crop.resize((w, 3000))
    crop.save(path)


def _module_entries(page):
    page.goto(URL, wait_until="networkidle")
    page.locator("h2#module-04--functions-and-generics").scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    return page.evaluate(
        """() => {
      const h2 = document.querySelector('h2#module-04--functions-and-generics');
      const out = [];
      let el = h2.nextElementSibling, cur = null;
      while (el && el.tagName !== 'H2') {
        if (el.tagName === 'H3') { cur = {h: el.innerText, paras: [], links: []}; out.push(cur); }
        else if (cur && el.tagName === 'P') cur.paras.push(el.innerText);
        else if (cur) cur.links.push(...[...el.querySelectorAll('a')].map(a => a.innerText));
        el = el.nextElementSibling;
      }
      return out;
    }"""
    )


def test_r5_module04_dom_metrics(cased_page):
    page, finalize = cased_page
    entries = _module_entries(page)
    vp = page.viewport_size
    tag = f"{vp['width']}x{vp['height']}"
    _module_shot(page, f"artifacts/test_r5_module04_dom_metrics/module04-{tag}.png")
    assert len(entries) >= 10, f"expected module 04 entries, got {len(entries)}"
    long, linkless = [], []
    for e in entries:
        for p in e["paras"]:
            if len(p.split()) > MAX_WORDS_PER_ENTRY_PARAGRAPH:
                long.append((e["h"][:40], len(p.split())))
        if not any("arrative" in t.lower() or re.match(r"^\d", t) for t in e["links"]):
            linkless.append(e["h"][:40])
    print(f"\nentries={len(entries)} overlong_paras={long} linkless={linkless}")
    assert not long, f"{len(long)} entry paragraphs exceed {MAX_WORDS_PER_ENTRY_PARAGRAPH} words"
    assert not linkless, f"entries with no narrative link: {linkless}"
    finalize()


def test_r5_module04_vision(cased_page):
    page, finalize = cased_page
    _module_entries(page)
    vp = page.viewport_size
    tag = f"{vp['width']}x{vp['height']}"
    shot = f"artifacts/test_r5_module04_vision/module04-{tag}.png"
    _module_shot(page, shot)
    page.locator("h2#module-04--functions-and-generics").screenshot(path=shot)
    with open(shot, "rb") as f:
        img = base64.b64encode(f.read()).decode()
    r = requests.post(
        OLLAMA_URL,
        json={
            "model": VISION_MODEL,
            "stream": False,
            "images": [img],
            "prompt": (
                "You are reviewing a documentation index page against the site design "
                "system: dark theme, carded content blocks, scannable hierarchy, one "
                "idea per block. Score READABILITY 1-5 (5 = scannable at a glance) "
                "and list the top 3 concrete visual defects hurting readability "
                "(walls of text, missing visual hierarchy, weak link affordance, "
                "poor spacing). Reply as: SCORE: <n> DEFECTS: <1>; <2>; <3>."
            ),
        },
        timeout=240,
    )
    text = r.json().get("response", "")
    print(f"\nvision verdict: {text[:400]}")
    m = re.search(r"SCORE:\s*([1-5])", text)
    assert m, f"no score parsed: {text[:200]}"
    assert int(m.group(1)) >= 4, f"readability score {m.group(1)} below bar 4: {text[:300]}"
    finalize()
