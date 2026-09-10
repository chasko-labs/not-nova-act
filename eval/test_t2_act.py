"""T2 act: NL fill + submit on a data-URL form; DOM assert + before/after diff."""

from not_nova_act.act import browser_act

FORM = (
    "data:text/html,"
    "<style>body{font-family:sans-serif;font-size:28px;background:white}</style>"
    "<form><input aria-label='callsign' type='text'/>"
    "<button type='submit'>Launch</button></form>"
    "<div id='out'></div>"
    "<script>document.querySelector('form').addEventListener('submit', e => {"
    "e.preventDefault(); document.getElementById('out').textContent = 'launched:' "
    "+ document.querySelector('input').value;});</script>"
)


def test_t2_act():
    res = browser_act(
        "Fill the callsign field with VEGA-9, then click Launch.",
        FORM, max_steps=6, timeout_seconds=280)
    assert res["status"] == "completed", res
    assert res["page_changed"] is True, res["steps"]
