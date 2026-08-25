"""`touchstone grade` over a run directory, the way a reader would use it.

Reads what `estimate` wrote and what `freeze` pinned, and writes `scorecard.json`. No
Docker and no network, because a grade has to be recomputable from a sealed bundle by
someone who has the bundle and nothing else.
"""

import json

from typer.testing import CliRunner

from touchstone.cli import app

runner = CliRunner()

ESTIMATES = {
    "touchstone_version": "test",
    "items": 400,
    "packs": ["example_pack"],
    "pooled": False,
    "estimates": [
        {
            "metric": "correct",
            "pack_id": "example_pack",
            "stratum": {},
            "n": 400,
            "point": 0.91,
            "low": 0.8783,
            "high": 0.9345,
            "k": 364,
            "estimator": "wilson",
            "parameters": {"z": 1.959963984540054},
            "reference": "Wilson 1927",
        }
    ],
}

LOCK = {
    "lock_format": 3,
    "plan_name": "example",
    "access_tier": "black_box",
    "root_seed": 7,
    "systems": {},
    "packs": [
        {
            "id": "example_pack",
            "image": "example_pack@sha256:" + "a" * 64,
            "calibrates": None,
            "emits_items": True,
            "seeds": [1],
        }
    ],
}

SCORE_CARD = """
score_card_name: "DQI test card"
levels: ["A", "B", "C", "D", "E", "F", "G", "H"]
tier_ceilings:
  black_box: "A"
indicators:
  - id: headline_accuracy
    name: "Headline accuracy with interval"
    metric: {source: estimate, name: correct, pack_id: example_pack}
    assessment:
      - {level: "A", condition: greater_equal_ci_lower, threshold: 0.90}
      - {level: "C", condition: greater_equal_ci_lower, threshold: 0.70}
"""


def build(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "estimates.json").write_text(json.dumps(ESTIMATES))
    (run_dir / "plan.lock.json").write_text(json.dumps(LOCK))
    (run_dir / "PLAN.sha256").write_text("2005a468" + "0" * 56 + "  plan.lock.json\n")
    card = tmp_path / "card.yaml"
    card.write_text(SCORE_CARD)
    return run_dir, card


def test_grade_writes_a_scorecard_and_reports_the_indeterminate_case(tmp_path):
    run_dir, card = build(tmp_path)

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 0, result.output
    assert "indeterminate" in result.output

    written = json.loads((run_dir / "scorecard.json").read_text())
    assert written["access_tier"] == "black_box"
    assert written["levels"] == ["A", "B", "C", "D", "E", "F", "G", "H"]
    assert written["plan_sha256"].startswith("2005a468")

    indicator = written["indicators"][0]
    assert indicator["verdict"] == "indeterminate"
    assert indicator["level"] is None
    assert indicator["between"] == ["A", "C"]


def test_the_access_tier_comes_from_the_frozen_plan_and_not_a_flag(tmp_path):
    """A grade is capped by the tier that was fixed before the run. Reading it from a flag
    would let the cap be chosen after seeing the result."""
    run_dir, card = build(tmp_path)
    (run_dir / "plan.lock.json").unlink()

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 1
    assert "access tier" in result.output


def test_a_score_card_naming_a_metric_that_never_ran_exits_non_zero(tmp_path):
    run_dir, card = build(tmp_path)
    card.write_text(SCORE_CARD.replace("name: correct", "name: never_reported"))

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 1
    assert "never_reported" in result.output
    assert not (run_dir / "scorecard.json").exists(), "a refused score card writes nothing"


def test_estimates_missing_says_which_command_to_run_first(tmp_path):
    run_dir, card = build(tmp_path)
    (run_dir / "estimates.json").unlink()

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 1
    assert "touchstone estimate" in result.output
