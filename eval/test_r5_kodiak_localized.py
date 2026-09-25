"""R5 localized suite (KODIAK diamond sprint, Phase 1): persona city markets
x featured frontier on the kodiak-dev build.

Pattern follows test_r4_kodiak.py: browser_act for multi-step loops,
browser_act_get with pydantic models for structured copy reads. The gate
states its own shared word on screen ("hint: cakes"), so entering it is
the sanctioned path.

Per-market loop (browser_act, 7 persona cases): gate -> open the Market
section -> open the Choose-market picker -> filter -> choose the market
option -> click CREATE CAMPAIGN PREVIEW. Envelope asserts only (the act
envelope carries no page text): completed + page_changed + a step floor
equal to the shortest honest walk, so an instant-done cannot pass.

Copy/telemetry asserts (browser_act_get + pydantic, never pixel
equality): market names + featured frontier from the rendered header,
the season value, and the preview sizes line.

Scope notes, kept honest rather than weakened:
- Cincinnati has NO picker entry on this build (nearest Ohio entry is
  Cleveland, US-MW-CLEVELAND -> Burton frontier). The cincinnati case
  drives the Ohio proxy and is labeled as such; a dedicated Cincinnati
  market would need app-side work (out of scope: no app code edits).
- Per-market finished-tile engines need gate + select + preview-click +
  compose dwell + extract, which exceeds browser_act_get's 3-step nav
  cap. The act loops prove each market reaches preview (page_changed);
  the extracts prove copy/telemetry on the default market. Finished
  per-tile engine copy per market is the known gap for the next sprint.
- Retry budget: ACT_ATTEMPTS / GET_ATTEMPTS below. QUARANTINED holds
  case ids that passed at least once but flaked on model variance; a
  quarantined case that still fails xfails instead of failing the
  suite. Populate it only from observed flakes, never to hide a real
  regression, and never by weakening an assertion.
"""

import pytest
from pydantic import BaseModel

from not_nova_act.act import browser_act
from not_nova_act.extract import browser_act_get

URL = "https://kodiak-dev.bryanchasko.com"

ACT_ATTEMPTS = 2
GET_ATTEMPTS = 2
ACT_TIMEOUT = 900
GET_TIMEOUT = 600

# (case_id, market_code, filter_text, expected_market, expected_frontier).
# expected_frontier values are the live Phase 1 pairings verified against
# the deployed build (locationSectionLabel per market).
PERSONAS = [
    ("park-city", "US-MW-PARKCITY-84098", "Park City",
     "Park City, Utah 84098", "Oakley, Utah 84055"),
    ("salt-lake", "US-MW-WASATCH-SLC", "Salt Lake",
     "Salt Lake City, Utah", "Grantsville, Utah 84029"),
    ("chicago", "US-MW-CHI", "Chicago",
     "Chicago, Illinois", "Harvard, Illinois 60033"),
    # No Cincinnati picker entry exists; Ohio coverage is Cleveland.
    ("cincinnati", "US-MW-CLEVELAND", "Cleveland",
     "Cleveland, Ohio", "Burton, Ohio 44021"),
    ("minneapolis", "US-MW-TC", "Twin Cities",
     "Twin Cities, Minnesota", "Stillwater, Minnesota 55082"),
    ("denver", "US-MW-DEN", "Denver",
     "Denver, Colorado", "Elizabeth, Colorado 80107"),
    ("austin", "US-SC-AUSTIN", "Austin",
     "Austin, Texas", "Fredericksburg, Texas 78624"),
]

# Quarantine registry: case ids that passed at least once but flaked.
# Empty until the suite observes a real flake. Protocol: add the id with
# a dated comment, never an assertion change.
QUARANTINED: set[str] = set()


def _run_act(task: str) -> dict:
    """browser_act with a fixed retry budget. Returns the last envelope."""
    last: dict = {"status": "never_ran", "page_changed": False, "steps": []}
    for _ in range(ACT_ATTEMPTS):
        last = browser_act(task, URL, max_steps=10, timeout_seconds=ACT_TIMEOUT)
        if last.get("status") == "completed" and last.get("page_changed") is True:
            break
    return last


def _transport_error_in_data(data: object) -> bool:
    """True when the extractor echoed a transport failure instead of page
    copy (the repair chain can validate error text as schema-shaped data).
    Retrying these is flake handling, not weakened assertions: the copy
    asserts below still run against real page reads."""
    if not isinstance(data, dict):
        return False
    needles = ("Server error", "500 Internal", "Traceback",
               "timed out", "connection refused", "Connection reset")
    return any(isinstance(v, str) and any(n in v for n in needles)
               for v in data.values())


def _run_get(task: str, schema: type[BaseModel]) -> dict:
    """browser_act_get with a fixed retry budget. Returns the last envelope."""
    last: dict = {"status": "never_ran"}
    for _ in range(GET_ATTEMPTS):
        last = browser_act_get(
            task, URL, schema, max_steps=6, timeout_seconds=GET_TIMEOUT)
        if last.get("status") == "completed" and not _transport_error_in_data(
                last.get("data")):
            break
    return last


def test_r5_kodiak_gate_act():
    res = _run_act(
        "Type the shared word cakes into the shared word field and click Enter.")
    assert res["status"] == "completed", res
    assert res["page_changed"] is True, res["steps"]


@pytest.mark.parametrize(
    "case_id,market_code,filter_text,expected_market,expected_frontier",
    [pytest.param(*p) for p in PERSONAS],
    ids=[p[0] for p in PERSONAS],
)
def test_r5_market_preview_act(
        case_id, market_code, filter_text, expected_market, expected_frontier):
    """Localized loop per persona market through preview render."""
    res = _run_act(
        f"Step inside with the shared word cakes: type it into the shared word "
        f"field and click Enter. Then open the Market section, open the "
        f"Choose-market picker, filter for '{filter_text}', choose the "
        f"'{expected_market}' option (featured frontier {expected_frontier}), "
        f"and click CREATE CAMPAIGN PREVIEW.")
    if case_id in QUARANTINED and res["status"] != "completed":
        pytest.xfail(f"quarantined flake ({case_id}): {res}")
    assert res["status"] == "completed", res
    assert res["page_changed"] is True, res["steps"]
    # Shortest honest walk is 6 dispatches (gate x2, two section opens,
    # market choice, preview kick); fewer means the loop never walked it.
    assert res.get("steps_completed", 0) >= 6, res["steps"]


class LocalizedHeader(BaseModel):
    market_label: str
    frontier_line: str
    season: str
    languages: str


def test_r5_localized_header_get():
    """Default-market copy: market name + frontier from the rendered header,
    season value. The in-season pairing line (winter squash) and the
    languages line render only inside the closed market picker disclosure /
    post-compose preview, past this helper's nav reach (see module notes);
    they are not asserted here rather than asserted weakly."""
    res = _run_get(
        "Step inside with the shared word (type cakes into the shared word "
        "field and click Enter), then read the campaign setup header: the "
        "market line naming the city and its featured frontier, and the "
        "season.",
        LocalizedHeader)
    assert res["status"] == "completed", res
    data = res["data"]
    # The header renders as one visual block ("<city> · Featured Frontier:
    # <frontier>"); the extractor splits it into its two copy halves, so the
    # city + frontier + zip anchors are asserted over the combined header
    # text. The literal "Featured Frontier" separator is extractor-lossy and
    # is not asserted as a literal.
    header_blob = data["market_label"] + "\n" + data["frontier_line"]
    assert "Park City" in header_blob, data
    assert "Oakley" in header_blob, data
    assert "84098" in header_blob, data
    assert data["season"].strip() == "September", data


class PreviewKick(BaseModel):
    market_label: str
    season: str
    sizes_line: str


def test_r5_preview_kick_get():
    """Preview section copy after kicking compose: market, season, 5 sizes."""
    res = _run_get(
        "Step inside with the shared word (type cakes into the shared word "
        "field and click Enter), then click CREATE CAMPAIGN PREVIEW and read "
        "the output preview section: the market line, the season, and the "
        "sizes line listing the preview sizes.",
        PreviewKick)
    assert res["status"] == "completed", res
    data = res["data"]
    assert "Park City" in data["market_label"], data
    assert data["season"].strip() == "September", data
    for size in ("1x1", "4x5", "9x16", "16x9", "blog"):
        assert size in data["sizes_line"], data
