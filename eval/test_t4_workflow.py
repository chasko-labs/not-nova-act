"""T4 workflow: goto -> act -> act_get sharing one context."""

from not_nova_act.workflow import run_workflow

FORM = (
    "data:text/html,"
    "<style>body{font-family:sans-serif;font-size:28px;background:white}</style>"
    "<h1>Badge Desk</h1>"
    "<form><input aria-label='callsign' type='text'/>"
    "<button type='submit'>Launch</button></form>"
    "<div id='out'></div>"
    "<script>document.querySelector('form').addEventListener('submit', e => {"
    "e.preventDefault(); document.getElementById('out').textContent = 'launched:' "
    "+ document.querySelector('input').value;});</script>"
)


def test_t4_workflow():
    res = run_workflow({
        "starting_page": FORM,
        "steps": [
            {"kind": "check", "checks": [
                {"type": "text_contains", "selector": "h1",
                 "expected": "Badge Desk"}]},
            {"kind": "act",
             "task": "Fill the callsign field with VEGA-9, then click Launch.",
             "max_steps": 6},
        ],
    })
    assert res["status"] == "completed", res
    assert [r["kind"] for r in res["results"]] == ["check", "act"]
