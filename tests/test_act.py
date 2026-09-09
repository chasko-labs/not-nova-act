"""Unit 3 validation: one NL form-fill on a data-URL page; page changes;
semaphore returns to baseline."""

from not_nova_act.act import browser_act
from not_nova_act.locks import SEMAPHORE_KEY, get_valkey

FORM = (
    "data:text/html,"
    "<form><input aria-label='callsign' type='text'/>"
    "<button type='submit'>Launch</button></form>"
    "<div id='out'></div>"
    "<script>document.querySelector('form').addEventListener('submit', e => {"
    "e.preventDefault(); document.getElementById('out').textContent = 'launched:' "
    "+ document.querySelector('input').value;});</script>"
)


def _sem_count():
    client = get_valkey()
    try:
        val = client.get(SEMAPHORE_KEY)
        return int(val) if val is not None else 0
    except Exception:
        return 0


def test_browser_act_fills_and_submits():
    assert _sem_count() == 0
    res = browser_act(
        "Fill the callsign field with the text VEGA-9, then click the Launch button.",
        FORM, max_steps=6, timeout_seconds=280)
    assert res["status"] == "completed", res
    assert res["page_changed"] is True, res["steps"]
    assert _sem_count() == 0, "semaphore must return to baseline"
