"""R3 real-site act_get: extract the sumerian start-beat heading."""

from pydantic import BaseModel

from not_nova_act.extract import browser_act_get


class Heading(BaseModel):
    heading: str


def test_r3_sumerian_heading():
    res = browser_act_get(
        "Read the game title heading on this start screen.",
        "https://bryanchasko.com/sumerian-squares/",
        Heading, max_steps=2, timeout_seconds=400)
    assert res["status"] == "completed", res
    assert "Sumerian" in res["data"]["heading"], res["data"]
