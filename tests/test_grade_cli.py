"""`touchstone grade` over a run directory, the way a reader would use it.

Reads what `estimate` wrote and what `freeze` pinned, and writes `scorecard.json`. No
Docker and no network, because a grade has to be recomputable from a sealed bundle by
someone who has the bundle and nothing else.
"""

import json

from typer.testing import CliRunner

from touchstone.cli import app

runner = CliRunner()


def test_grade_writes_a_scorecard_and_reports_the_indeterminate_case(graded):
    run_dir, card = graded

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


def test_the_access_tier_comes_from_the_frozen_plan_and_not_a_flag(graded):
    """A grade is capped by the tier that was fixed before the run. Reading it from a flag
    would let the cap be chosen after seeing the result."""
    run_dir, card = graded
    (run_dir / "plan.lock.json").unlink()

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 1
    assert "access tier" in result.output


def test_a_score_card_naming_a_metric_that_never_ran_exits_non_zero(graded):
    run_dir, card = graded
    card.write_text(card.read_text().replace("name: correct", "name: never_reported"))

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 1
    assert "never_reported" in result.output
    assert not (run_dir / "scorecard.json").exists(), "a refused score card writes nothing"


def test_estimates_missing_says_which_command_to_run_first(graded):
    run_dir, card = graded
    (run_dir / "estimates.json").unlink()

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 1
    assert "touchstone estimate" in result.output
