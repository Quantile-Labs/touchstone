"""The verdict M3 exists for.

`03-BUILD-PLAN.md` M3: "A grade asserted on a point estimate whose interval spans the
boundary is reported as indeterminate, not as the better grade."

Every test here is a case where grading the point estimate alone would give a confident
answer and the interval says the evidence does not support one. ASQI's `AssessmentRule`
compares a metric to a threshold and has nowhere to put this, which is why the milestone
is not "port the score card engine".
"""

import pytest

from touchstone.contracts.estimates import Estimate, Estimates
from touchstone.contracts.scorecard import ScoreCard
from touchstone.errors import ScoreCardError
from touchstone.grade import grade

LEVELS = ["A", "B", "C", "D", "E", "F", "G", "H"]
"""Eight, per `03-BUILD-PLAN.md` M3, and named nowhere in `src/`. The engine reads the
ladder off the score card, so a three level card or ASQI's five work unchanged."""


def estimates(point: float, low: float, high: float, n: int = 400) -> Estimates:
    return Estimates(
        touchstone_version="test",
        items=n,
        packs=["procedural_ng"],
        estimates=[
            Estimate(
                metric="correct",
                pack_id="procedural_ng",
                n=n,
                point=point,
                low=low,
                high=high,
                k=int(round(point * n)),
                estimator="wilson",
                reference="Wilson 1927",
            )
        ],
    )


def score_card(tier_ceilings: dict[str, str] | None = None) -> ScoreCard:
    return ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        tier_ceilings=tier_ceilings or {},
        indicators=[
            {
                "id": "headline_accuracy",
                "metric": {"source": "estimate", "name": "correct", "pack_id": "procedural_ng"},
                "assessment": [
                    {"level": "A", "condition": "greater_equal_ci_lower", "threshold": 0.90},
                    {"level": "C", "condition": "greater_equal_ci_lower", "threshold": 0.70},
                ],
            }
        ],
    )


def only(card: ScoreCard, run: Estimates, tier: str = "black_box"):
    return grade(card, run, tier).indicators[0]


def test_interval_spanning_the_boundary_is_indeterminate():
    """The point estimate clears 0.90. The lower bound does not. Grading the point alone
    awards A, and the run cannot distinguish A from C."""
    verdict = only(score_card(), estimates(point=0.91, low=0.87, high=0.94))

    assert verdict.verdict == "indeterminate"
    assert verdict.level is None, "an indeterminate indicator must not carry a level"
    assert verdict.between == ["A", "C"]
    assert "0.9" in (verdict.reason or "")


def test_the_whole_interval_clearing_the_bar_is_graded():
    verdict = only(score_card(), estimates(point=0.95, low=0.92, high=0.97))

    assert verdict.verdict == "graded"
    assert verdict.level == "A"


def test_the_whole_interval_below_the_bar_falls_through_rather_than_stalling():
    """Indeterminate is for an overlap, not for any failure to reach the top rung."""
    verdict = only(score_card(), estimates(point=0.80, low=0.76, high=0.84))

    assert verdict.verdict == "graded"
    assert verdict.level == "C"


def test_a_straddle_with_nothing_below_it_says_so():
    """Nothing lower holds, so the honest range is open at the bottom."""
    verdict = only(score_card(), estimates(point=0.71, low=0.66, high=0.75))

    assert verdict.verdict == "indeterminate"
    assert verdict.between == ["C"]
    assert "no grade at all" in (verdict.reason or "")


def test_an_empty_cell_is_ungraded_and_not_the_worst_level():
    """A denominator of zero is missing evidence. Scoring it H would be an assertion
    about a system nobody measured."""
    run = estimates(point=0.9, low=0.8, high=0.95)
    run.estimates[0].n = 0
    run.estimates[0].point = None

    verdict = only(score_card(), run)

    assert verdict.verdict == "ungraded"
    assert verdict.level is None
    assert "nothing to grade" in (verdict.reason or "")


def test_a_tier_ceiling_below_both_ends_settles_the_indeterminacy():
    """Black box caps at C, and the range was A to C, so the ceiling decides it either
    way and there is nothing left for the interval to decide."""
    card = score_card(tier_ceilings={"black_box": "C", "white_box": "A"})
    verdict = only(card, estimates(point=0.91, low=0.87, high=0.94))

    assert verdict.verdict == "graded"
    assert verdict.level == "C"
    assert verdict.ceiling_reason == "access_tier"
    assert verdict.uncapped_level == "A"


def test_the_same_evidence_at_a_higher_tier_stays_indeterminate():
    card = score_card(tier_ceilings={"black_box": "C", "white_box": "A"})
    verdict = only(card, estimates(point=0.91, low=0.87, high=0.94), tier="white_box")

    assert verdict.verdict == "indeterminate"
    assert verdict.between == ["A", "C"]


def test_an_unrecognised_tier_is_refused_rather_than_left_uncapped():
    card = score_card(tier_ceilings={"black_box": "C"})
    with pytest.raises(ScoreCardError, match="grey_box"):
        grade(card, estimates(point=0.95, low=0.92, high=0.97), "grey_box")


def lower_is_better_card() -> ScoreCard:
    """Confident-and-wrong rate: the claim is that it is small, so the level is only
    earned when the whole interval sits below the threshold."""
    return ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        indicators=[
            {
                "id": "confident_and_wrong",
                "metric": {"source": "estimate", "name": "correct", "pack_id": "procedural_ng"},
                "assessment": [
                    {"level": "A", "condition": "less_equal_ci_upper", "threshold": 0.02},
                    {"level": "C", "condition": "less_equal_ci_upper", "threshold": 0.10},
                ],
            }
        ],
    )


def test_less_equal_ci_upper_awards_only_when_the_whole_interval_is_below():
    verdict = only(lower_is_better_card(), estimates(point=0.008, low=0.003, high=0.017))

    assert verdict.verdict == "graded"
    assert verdict.level == "A"


def test_less_equal_ci_upper_is_indeterminate_across_its_boundary():
    """The point estimate is under 0.02 and the upper bound is not, so a report claiming A
    would be claiming the rate is small on evidence that does not exclude it being twice
    the threshold."""
    verdict = only(lower_is_better_card(), estimates(point=0.018, low=0.011, high=0.031))

    assert verdict.verdict == "indeterminate"
    assert verdict.between == ["A", "C"]


def test_less_equal_ci_upper_falls_through_when_the_whole_interval_is_above():
    verdict = only(lower_is_better_card(), estimates(point=0.06, low=0.04, high=0.09))

    assert verdict.verdict == "graded"
    assert verdict.level == "C"


def test_threshold_crossed_by_interval_can_be_named_as_its_own_level():
    """The straddle as an explicit rung, for a score card that would rather say `D, the
    evidence is too thin to separate these` than report a range."""
    card = ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        indicators=[
            {
                "id": "headline_accuracy",
                "metric": {"source": "estimate", "name": "correct", "pack_id": "procedural_ng"},
                "assessment": [
                    {"level": "A", "condition": "greater_equal_ci_lower", "threshold": 0.90},
                    {"level": "D", "condition": "threshold_crossed_by_interval", "threshold": 0.90},
                ],
            }
        ],
    )
    verdict = only(card, estimates(point=0.91, low=0.87, high=0.94))

    assert verdict.verdict == "indeterminate", (
        "the A rule still straddles, and it is read before the rule that names the straddle"
    )
    assert verdict.between == ["A", "D"]
