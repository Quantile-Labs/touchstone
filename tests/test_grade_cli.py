"""`touchstone grade` over a run directory, the way a reader would use it.

Reads what `estimate` wrote and what `freeze` pinned, and writes `scorecard.json`. No
Docker and no network, because a grade has to be recomputable from a sealed bundle by
someone who has the bundle and nothing else.
"""

import json

from typer.testing import CliRunner

from touchstone import bundle
from touchstone.cli import app

runner = CliRunner()


def test_grade_writes_a_scorecard_and_reports_the_indeterminate_case(graded):
    run_dir, card = graded

    result = runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card)])

    assert result.exit_code == 0, result.output
    assert "Grade: A or C, inconclusive" in result.output

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


def _grade(run_dir, card, *extra):
    return runner.invoke(app, ["grade", str(run_dir), "--score-card", str(card), *extra])


def test_grading_a_sealed_bundle_is_refused_and_leaves_it_verifying(graded):
    """Grading a bundle somebody was handed must not break the evidence they were handed."""
    run_dir, card = graded
    bundle.seal(run_dir)

    result = _grade(run_dir, card)

    assert result.exit_code == 1
    assert "is sealed" in result.output
    assert "--out" in result.output
    assert not (run_dir / "scorecard.json").exists()
    assert bundle.verify(run_dir) == []


def test_out_grades_a_sealed_bundle_without_touching_it(graded, tmp_path):
    run_dir, card = graded
    bundle.seal(run_dir)
    mine = tmp_path / "mine"

    result = _grade(run_dir, card, "--out", str(mine))

    assert result.exit_code == 0, result.output
    assert (mine / "scorecard.json").is_file()
    assert f"Estimates: {run_dir / 'estimates.json'}" in result.output
    assert bundle.verify(run_dir) == []


def test_out_holding_estimates_is_graded_in_place_of_the_bundles(graded, tmp_path):
    """Re-estimate beside a sealed bundle, then grade what was re-estimated."""
    run_dir, card = graded
    mine = tmp_path / "mine"
    mine.mkdir()
    narrower = json.loads((run_dir / "estimates.json").read_text())
    narrower["estimates"][0] |= {"point": 0.94, "low": 0.92, "high": 0.96, "k": 376}
    (mine / "estimates.json").write_text(json.dumps(narrower))

    result = _grade(run_dir, card, "--out", str(mine))

    assert result.exit_code == 0, result.output
    assert f"Estimates: {mine / 'estimates.json'}" in result.output
    indicator = json.loads((mine / "scorecard.json").read_text())["indicators"][0]
    assert (indicator["verdict"], indicator["level"]) == ("graded", "A")


def test_out_inside_a_sealed_bundle_is_refused(graded):
    run_dir, card = graded
    bundle.seal(run_dir)

    result = _grade(run_dir, card, "--out", str(run_dir / "analysis"))

    assert result.exit_code == 1
    assert not (run_dir / "analysis").exists()
    assert bundle.verify(run_dir) == []


def test_a_sealed_refusal_carries_its_own_code(graded):
    run_dir, card = graded
    bundle.seal(run_dir)

    result = _grade(run_dir, card, "--json")

    assert result.exit_code == 1
    assert [problem["code"] for problem in json.loads(result.stdout)["problems"]] == [
        "bundle_sealed"
    ]
