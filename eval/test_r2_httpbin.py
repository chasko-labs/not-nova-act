"""R2 real-site act: fill the httpbin customer form and submit.
Echo page must change; validates grounding on real labeled inputs."""

from not_nova_act.act import browser_act


def test_r2_httpbin_form():
    res = browser_act(
        "Fill the Customer name field with Ada Lovelace, then click Submit.",
        "https://httpbin.org/forms/post", max_steps=6, timeout_seconds=280)
    assert res["status"] == "completed", res
    assert res["page_changed"] is True, res["steps"]
