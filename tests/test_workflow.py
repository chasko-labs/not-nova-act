"""Unit 6 validation: 3-step YAML def shares context across steps.
Model-free steps only (act/act_get integration is proven in units 3-4
and exercised end to end by T4 in unit 7)."""

from not_nova_act.workflow import load_def, run_workflow

DEF = """
starting_page: https://example.com
steps:
  - kind: check
    checks:
      - {type: text_contains, selector: h1, expected: Example Domain}
  - kind: screenshot
  - kind: assert
    task: starting_page==https://example.com
"""


def test_workflow_shares_context(tmp_path):
    defn = load_def(_write(tmp_path))
    assert defn["starting_page"] == "https://example.com"
    res = run_workflow(defn)
    assert res["status"] == "completed", res
    assert [r["kind"] for r in res["results"]] == ["check", "screenshot", "assert"]
    assert all(r["status"] == "completed" for r in res["results"])
    assert res["context"]["starting_page"] == "https://example.com"


def _write(tmp_path):
    p = tmp_path / "wf.yaml"
    p.write_text(DEF)
    return str(p)


def test_workflow_passes_viewport_and_mobile_to_steps():
    """Per-step render width: mobile check sees innerWidth 375, and a
    768-wide screenshot step completes. Steps without viewport keys keep
    the 1280 desktop default (covered by test_workflow_shares_context)."""
    defn = {
        "starting_page": "https://example.com",
        "steps": [
            {"kind": "check",
             "viewport": {"width": 375, "height": 812},
             "mobile": True,
             "checks": [
                 {"type": "evaluate", "expression": "window.innerWidth",
                  "expected": 375,
                  "description": "mobile emulation tracks viewport width"},
             ]},
            {"kind": "screenshot", "viewport": {"width": 768, "height": 900}},
        ],
    }
    res = run_workflow(defn)
    assert res["status"] == "completed", res
    assert [r["kind"] for r in res["results"]] == ["check", "screenshot"]
