"""Grading movement between two bundles, which is the one thing here that reads two.

Every other command is a pure function of one bundle and stays that way. `drift_since_last`
is not, so which numbers came from where is written in the score card rather than implied
by a flag, and `scorecard.json` names both frozen plans. Movement between two evaluations
run under different plans is movement in the plan as much as in the system, and a reader
is entitled to see that before quoting the drift.
"""

import json

import pytest
from test_grade import LEVELS, bundle, rate
from typer.testing import CliRunner

from touchstone.cli import app
from touchstone.contracts.scorecard import ScoreCard
from touchstone.grade import Prior, check, grade, lines

runner = CliRunner()

DRIFT = {
    "expression": "abs(now - before)",
    "values": {
        "now": {"name": "correct", "pack_id": "procedural_ng"},
        "before": {"bundle": "prior", "name": "correct", "pack_id": "procedural_ng"},
    },
}

ASSESSMENT = [
    {"level": "A", "condition": "less_equal", "threshold": 0.02},
    {"level": "C", "condition": "less_equal", "threshold": 0.10},
]


def card(metric=None, assessment=None):
    return ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        indicators=[
            {
                "id": "drift_since_last",
                "metric": metric or DRIFT,
                "assessment": assessment or ASSESSMENT,
            }
        ],
    )


def prior(point=0.90):
    return Prior(estimates=bundle(rate("correct", point, point - 0.04, point + 0.03)))


def test_a_first_evaluation_is_ungraded_rather_than_failed():
    """There is nothing to have moved from. Grading it as the worst level would report a
    system that drifted, and grading it as the best would report one that held."""
    scored = grade(card(), bundle(rate("correct", 0.93, 0.89, 0.955)), "black_box").indicators[0]

    assert scored.verdict == "ungraded"
    assert "--prior" in scored.reason


def test_a_first_evaluation_is_not_a_broken_reference():
    """`check` refuses a metric that was never computed. A prior reference with no prior
    bundle is a different thing, and reporting it as a broken card would stop the whole
    grade over an indicator that is merely not yet answerable."""
    assert check(card(), bundle(rate("correct", 0.93, 0.89, 0.955)), "black_box") == []


def test_movement_is_graded_against_the_earlier_bundle():
    scorecard = grade(
        card(),
        bundle(rate("correct", 0.93, 0.89, 0.955)),
        "black_box",
        prior=prior(0.90),
    )
    scored = scorecard.indicators[0]

    assert scored.verdict == "graded"
    assert scored.value == pytest.approx(0.03)
    assert scored.level == "C", "0.03 clears the 0.10 rung and not the 0.02 one"
    assert "0.03 = abs(now - before)" in lines(scorecard)[0]


def test_a_metric_absent_from_the_earlier_bundle_says_which_bundle():
    problems = check(
        card(),
        bundle(rate("correct", 0.93, 0.89, 0.955)),
        "black_box",
        prior=Prior(estimates=bundle(rate("covered", 0.5, 0.44, 0.56))),
    )

    assert any("the prior bundle" in problem.message for problem in problems)


def test_both_plan_hashes_are_recorded():
    scorecard = grade(
        card(),
        bundle(rate("correct", 0.93, 0.89, 0.955)),
        "black_box",
        plan_sha256="a" * 64,
        prior=Prior(estimates=bundle(rate("correct", 0.9, 0.86, 0.93)), plan_sha256="b" * 64),
    )

    assert scorecard.plan_sha256 == "a" * 64
    assert scorecard.prior_plan_sha256 == "b" * 64


SCORE_CARD = """
score_card_name: "drift card"
levels: ["A", "B", "C", "D"]
tier_ceilings:
  black_box: "A"
indicators:
  - id: drift_since_last
    metric:
      expression: "abs(now - before)"
      values:
        now: {name: correct, pack_id: example_pack}
        before: {bundle: prior, name: correct, pack_id: example_pack}
    assessment:
      - {level: "A", condition: less_equal, threshold: 0.02}
      - {level: "C", condition: less_equal, threshold: 0.10}
"""


def build(tmp_path, name, point):
    from conftest import ESTIMATES, LOCK

    estimates = json.loads(json.dumps(ESTIMATES))
    estimates["estimates"][0]["point"] = point
    directory = tmp_path / name
    directory.mkdir()
    (directory / "estimates.json").write_text(json.dumps(estimates))
    (directory / "plan.lock.json").write_text(json.dumps(LOCK))
    (directory / "PLAN.sha256").write_text("2005a468" + "0" * 56 + "  plan.lock.json\n")
    return directory


def test_the_cli_grades_one_bundle_against_another(tmp_path):
    now = build(tmp_path, "now", 0.93)
    before = build(tmp_path, "before", 0.90)
    card_path = tmp_path / "card.yaml"
    card_path.write_text(SCORE_CARD)

    result = runner.invoke(
        app, ["grade", str(now), "--score-card", str(card_path), "--prior", str(before)]
    )

    assert result.exit_code == 0, result.output
    written = json.loads((now / "scorecard.json").read_text())
    assert written["indicators"][0]["value"] == pytest.approx(0.03)
    assert written["prior_plan_sha256"].startswith("2005a468")


def test_a_bundle_compared_against_itself_is_refused(tmp_path):
    """Zero by construction, and it would read as a system that has not drifted."""
    now = build(tmp_path, "now", 0.93)
    card_path = tmp_path / "card.yaml"
    card_path.write_text(SCORE_CARD)

    result = runner.invoke(
        app, ["grade", str(now), "--score-card", str(card_path), "--prior", str(now)]
    )

    assert result.exit_code == 1
    assert "against itself" in result.output
