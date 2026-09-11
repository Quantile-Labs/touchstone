"""Grading movement between two bundles, which is the one thing here that reads two.

Every other command is a pure function of one bundle and stays that way. `drift_since_last`
is not, so which numbers came from where is written in the score card rather than implied
by a flag, and `scorecard.json` names both frozen plans. Movement between two evaluations
run under different plans is movement in the plan as much as in the system, and a reader
is entitled to see that before quoting the drift.
"""

import json
from math import sqrt
from statistics import fmean, stdev

import pytest
from pydantic import ValidationError
from test_grade import LEVELS, bundle, rate
from typer.testing import CliRunner

from touchstone.cli import app
from touchstone.contracts import ItemRecord
from touchstone.contracts.scorecard import MetricRef, ScoreCard
from touchstone.estimate import estimate, write_estimates
from touchstone.grade import Prior, check, grade, lines
from touchstone.stats.proportion import Z_95

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
    assert "Score: 0.03 (abs(now - before))" in "\n".join(lines(scorecard))


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
    assert "is the bundle being graded" in result.output


PAIRED = {"source": "paired_difference", "name": "correct", "pack_id": "example_pack"}

HELD = [
    {"level": "A", "condition": "greater_equal_ci_lower", "threshold": 0.0},
    {"level": "C", "condition": "greater_equal", "threshold": -0.10},
]

PLAN_A = "a" * 64

BEFORE = [True] * 70 + [False] * 30
NOW = [True] * 75 + [False] * 25
"""The same seventy items right both times and five more right now. Two runs that agree
this closely about which items are hard are what pairing exists for."""


def records(outcomes, pack="example_pack"):
    return [
        ItemRecord(item_id=f"q.{index:03d}", outcome={"correct": correct}, pack_id=pack)
        for index, correct in enumerate(outcomes)
    ]


def movement(now=NOW, before=BEFORE, plan=PLAN_A, prior_plan=PLAN_A, prior_items=True):
    now_items, before_items = records(now), records(before)
    return grade(
        card(PAIRED, HELD),
        estimate(now_items),
        "black_box",
        plan_sha256=plan,
        prior=Prior(
            estimates=estimate(before_items),
            plan_sha256=prior_plan,
            items=before_items if prior_items else None,
        ),
        items=now_items,
    )


def test_movement_over_the_same_plan_and_items_is_paired():
    scorecard = movement()
    scored = scorecard.indicators[0]
    measured = scored.measured[0]

    differences = [1.0] * 5 + [0.0] * 95
    error = stdev(differences) / sqrt(len(differences))
    assert measured.difference.comparison == "paired"
    assert measured.value == pytest.approx(fmean(differences))
    assert measured.low == pytest.approx(0.05 - Z_95 * error)
    assert measured.difference.parameters["items"] == 100
    assert scored.level == "A", "the whole paired interval sits above no change"


def test_different_plans_fall_back_to_unpaired_and_the_interval_widens():
    paired = movement().indicators[0].measured[0]
    scored = movement(prior_plan="b" * 64).indicators[0]
    unpaired = scored.measured[0]

    assert unpaired.difference.comparison == "unpaired"
    assert "different plans" in unpaired.difference.reason
    assert unpaired.difference.estimator == "wilson_difference"
    assert unpaired.value == pytest.approx(paired.value)
    assert unpaired.high - unpaired.low > paired.high - paired.low
    assert scored.verdict == "indeterminate", "the wider interval straddles no change"


def test_the_same_plan_with_different_items_is_not_paired():
    """A unit that failed in one run leaves the plan hash identical and the items not."""
    measured = movement(now=NOW[:-1]).indicators[0].measured[0]
    assert measured.difference.comparison == "unpaired"
    assert "appear in only one test" in measured.difference.reason


def test_a_prior_bundle_without_items_is_not_paired():
    measured = movement(prior_items=False).indicators[0].measured[0]
    assert measured.difference.comparison == "unpaired"
    assert measured.difference.reason == (
        "the previous test has no item-level results (items.jsonl)"
    )


def test_a_missing_plan_hash_is_not_paired():
    measured = movement(plan=None).indicators[0].measured[0]
    assert measured.difference.comparison == "unpaired"
    assert "does not record its plan" in measured.difference.reason


def test_a_paired_difference_without_a_prior_is_ungraded_and_not_a_broken_card():
    now = estimate(records(NOW))
    assert check(card(PAIRED, HELD), now, "black_box") == []
    scored = grade(card(PAIRED, HELD), now, "black_box").indicators[0]
    assert scored.verdict == "ungraded"
    assert "--prior" in scored.reason


def test_an_interval_condition_on_a_paired_difference_is_allowed():
    before = estimate(records(BEFORE))
    problems = check(card(PAIRED, HELD), estimate(records(NOW)), "black_box", prior=Prior(before))
    assert problems == []


def test_a_paired_difference_naming_the_prior_bundle_is_refused():
    with pytest.raises(ValidationError, match="reads both bundles"):
        MetricRef.model_validate(PAIRED | {"bundle": "prior"})


def test_the_printed_grade_says_which_comparison_ran():
    assert "compared item by item" in "\n".join(lines(movement()))

    printed = lines(movement(prior_plan="b" * 64))
    assert "compared item by item" not in "\n".join(printed)
    assert any(
        line.startswith("  Compared by totals: the tests used different plans") for line in printed
    )


PAIRED_CARD = """
score_card_name: "paired card"
levels: ["A", "B", "C", "D"]
tier_ceilings:
  black_box: "A"
indicators:
  - id: accuracy_held
    metric: {source: paired_difference, name: correct, pack_id: example_pack}
    assessment:
      - {level: "A", condition: greater_equal_ci_lower, threshold: 0.0}
      - {level: "C", condition: greater_equal, threshold: -0.10}
"""


def run_with_items(tmp_path, name, outcomes):
    from conftest import LOCK

    directory = tmp_path / name
    directory.mkdir()
    rows = records(outcomes)
    (directory / "items.jsonl").write_text("".join(row.model_dump_json() + "\n" for row in rows))
    write_estimates(estimate(rows), directory)
    (directory / "plan.lock.json").write_text(json.dumps(LOCK))
    (directory / "PLAN.sha256").write_text(PLAN_A + "  plan.lock.json\n")
    return directory


def test_the_cli_pairs_two_runs_of_the_same_plan(tmp_path):
    now = run_with_items(tmp_path, "now", NOW)
    before = run_with_items(tmp_path, "before", BEFORE)
    card_path = tmp_path / "card.yaml"
    card_path.write_text(PAIRED_CARD)

    result = runner.invoke(
        app, ["grade", str(now), "--score-card", str(card_path), "--prior", str(before)]
    )

    assert result.exit_code == 0, result.output
    written = json.loads((now / "scorecard.json").read_text())
    measured = written["indicators"][0]["measured"][0]
    assert measured["difference"]["comparison"] == "paired"
    assert measured["difference"]["reference"].startswith("Miller")
    assert written["indicators"][0]["level"] == "A"
