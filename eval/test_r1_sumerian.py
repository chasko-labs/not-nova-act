"""R1 real-site: sumerian-squares start beat on every viewport.
Start-beat contract: title, name field, and Begin affordance visible;
zero page errors; screenshot artifacts per viewport."""

from not_nova_act import run_checks


def test_r1_sumerian_start_beat(cased_page):
    page, finalize = cased_page
    page.goto("https://bryanchasko.com/sumerian-squares/",
              wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)
    res = run_checks(page, [
        {"type": "text_contains", "selector": "h2.sh-start__title",
         "expected": "Sumerian Squares"},
        {"type": "exists", "selector": "#sh-start-name"},
        {"type": "exists", "selector": ".sh-start__begin"},
    ])
    outdir, events = finalize()
    assert res["all_passed"], res["results"]
    assert events["pageerror"] == [], events["pageerror"]
    assert (outdir / "final.png").stat().st_size > 0
