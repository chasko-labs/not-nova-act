"""R4 real-site: kodiak courtesy gate + wizard. The gate states its own
shared word on screen ("hint: cakes", "a courtesy screen, not security"),
so entering it is the sanctioned path and a true multi-step loop test."""

from pydantic import BaseModel

from not_nova_act.act import browser_act
from not_nova_act.extract import browser_act_get

URL = "https://kodiak.bryanchasko.com"


class Heading(BaseModel):
    heading: str


def test_r4_kodiak_gate_act():
    res = browser_act(
        "Type the shared word cakes into the shared word field and click Enter.",
        URL, max_steps=6, timeout_seconds=280)
    assert res["status"] == "completed", res
    assert res["page_changed"] is True, res["steps"]


def test_r4_kodiak_wizard_extract():
    res = browser_act_get(
        "Step inside with the shared word, then read the main page heading.",
        URL, Heading, max_steps=6, timeout_seconds=400)
    assert res["status"] == "completed", res
    assert "Kodiak" in res["data"]["heading"], res["data"]
