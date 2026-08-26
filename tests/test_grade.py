"""Everything `grade` refuses, and the sources it grades.

The refusals matter more than the grades. ASQI enforces its id pattern on a test
definition and not on the score card filter that references one, so a score card there can
name a test that never ran and the indicator scores nothing without saying so
(01-ASQI-TEARDOWN.md section 4, defect 3). Every case below is that class of defect made
into an error.
"""

import pytest

from touchstone.contracts.estimates import Calibration, Estimate, Estimates
from touchstone.contracts.scorecard import ScoreCard
from touchstone.errors import ScoreCardError
from touchstone.grade import check, grade

LEVELS = ["A", "B", "C", "D"]


def rate(metric, point, low, high, n=200, pack="procedural_ng", stratum=None):
    """A Wilson estimate carrying its counts, because `k` is what a Wilson estimate is."""
    return Estimate(
        metric=metric,
        pack_id=pack,
        stratum=stratum or {},
        n=n,
        k=round(point * n),
        point=point,
        low=low,
        high=high,
        estimator="wilson",
        reference="Wilson 1927",
    )


def bundle(*estimates, packs=("procedural_ng",), calibration=(), pooled=False):
    return Estimates(
        touchstone_version="test",
        items=200,
        packs=list(packs),
        pooled=pooled,
        estimates=list(estimates),
        calibration=list(calibration),
    )


def card(metric, assessment, **extra):
    return ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        indicators=[{"id": "indicator", "metric": metric, "assessment": assessment}],
        **extra,
    )


PASSES = [{"level": "A", "condition": "greater_equal", "threshold": 0.5}]


def test_a_metric_that_was_never_computed_is_an_error_not_a_zero():
    problems = check(
        card({"name": "never_reported", "pack_id": "procedural_ng"}, PASSES),
        bundle(rate("correct", 0.9, 0.85, 0.93)),
    )
    assert problems
    assert "never_reported" in problems[0]
    assert "not a zero" in problems[0]


def test_a_pack_that_never_ran_is_an_error():
    problems = check(
        card({"name": "correct", "pack_id": "some_other_pack"}, PASSES),
        bundle(rate("correct", 0.9, 0.85, 0.93)),
    )
    assert any("some_other_pack" in problem for problem in problems)


def test_an_interval_condition_against_a_source_with_no_interval_is_refused():
    """An ECE is a single number. Asking whether its lower bound clears a threshold is a
    question about an interval this codebase never computed."""
    problems = check(
        card(
            {"source": "calibration", "name": "correct", "pack_id": "procedural_ng"},
            [{"level": "A", "condition": "greater_equal_ci_lower", "threshold": 0.5}],
        ),
        bundle(
            rate("correct", 0.9, 0.85, 0.93),
            calibration=[
                Calibration(
                    metric="correct",
                    pack_id="procedural_ng",
                    n=200,
                    ece=0.04,
                    reference="Naeini 2015",
                )
            ],
        ),
    )
    assert any("carries no interval" in problem for problem in problems)


def test_an_interval_condition_against_an_expression_is_refused():
    problems = check(
        card(
            {
                "expression": "a * 2",
                "values": {"a": {"name": "correct", "pack_id": "procedural_ng"}},
            },
            [{"level": "A", "condition": "greater_equal_ci_lower", "threshold": 0.5}],
        ),
        bundle(rate("correct", 0.9, 0.85, 0.93)),
    )
    assert any("no interval by design" in problem for problem in problems)


def test_an_expression_variable_with_no_value_is_refused():
    problems = check(
        card(
            {
                "expression": "a + b",
                "values": {"a": {"name": "correct", "pack_id": "procedural_ng"}},
            },
            PASSES,
        ),
        bundle(rate("correct", 0.9, 0.85, 0.93)),
    )
    assert any("'b' is in the expression and not in values" in problem for problem in problems)


def test_a_declared_value_the_expression_never_reads_is_refused():
    """A leftover after a rename reads as evidence that was considered and was not."""
    problems = check(
        card(
            {
                "expression": "a",
                "values": {
                    "a": {"name": "correct", "pack_id": "procedural_ng"},
                    "stale": {"name": "correct", "pack_id": "procedural_ng"},
                },
            },
            PASSES,
        ),
        bundle(rate("correct", 0.9, 0.85, 0.93)),
    )
    assert any("'stale' is in values and not in the expression" in problem for problem in problems)


def test_a_pooled_figure_on_a_multi_pack_run_has_to_name_its_pack():
    problems = check(
        card({"name": "correct"}, PASSES),
        bundle(
            rate("correct", 0.9, 0.85, 0.93, pack=None),
            packs=("procedural_ng", "asqi_thing"),
            pooled=True,
        ),
    )
    assert any("Name a pack" in problem for problem in problems)


def test_a_clean_score_card_reports_no_problems():
    assert (
        check(
            card({"name": "correct", "pack_id": "procedural_ng"}, PASSES),
            bundle(rate("correct", 0.9, 0.85, 0.93)),
        )
        == []
    )


def test_an_expression_grades_on_its_combined_value():
    scored = grade(
        card(
            {
                "expression": "0.5 * acc + 0.5 * cov",
                "values": {
                    "acc": {"name": "correct", "pack_id": "procedural_ng"},
                    "cov": {"name": "covered", "pack_id": "procedural_ng"},
                },
            },
            [
                {"level": "A", "condition": "greater_equal", "threshold": 0.8},
                {"level": "B", "condition": "greater_equal", "threshold": 0.6},
            ],
        ),
        bundle(rate("correct", 0.9, 0.85, 0.93), rate("covered", 0.5, 0.44, 0.56)),
        "black_box",
    ).indicators[0]

    assert scored.verdict == "graded"
    assert scored.level == "B"
    assert scored.expression == "0.5 * acc + 0.5 * cov"
    assert len(scored.measured) == 2
    assert all(one.low is not None for one in scored.measured), (
        "each input keeps the interval it was estimated with, so a reader can see what "
        "went in. It is the combined value that has none, which is why check() refuses an "
        "interval condition against an expression"
    )


def test_summary_only_evidence_is_capped():
    """02-DESIGN.md section 3.4: a pack that emitted no items may not carry a grade above
    the ceiling, however good the number it asserted looks."""
    scored = grade(
        card({"name": "correct", "pack_id": "asqi_thing"}, PASSES, summary_only_ceiling="C"),
        bundle(rate("correct", 0.99, 0.97, 1.0, pack="asqi_thing"), packs=("asqi_thing",)),
        "black_box",
        summary_only=frozenset({"asqi_thing"}),
    ).indicators[0]

    assert scored.level == "C"
    assert scored.uncapped_level == "A"
    assert scored.ceiling_reason == "summary_only"


def test_the_harder_of_the_two_ceilings_is_the_one_that_binds():
    scored = grade(
        card(
            {"name": "correct", "pack_id": "asqi_thing"},
            PASSES,
            summary_only_ceiling="C",
            tier_ceilings={"black_box": "B"},
        ),
        bundle(rate("correct", 0.99, 0.97, 1.0, pack="asqi_thing"), packs=("asqi_thing",)),
        "black_box",
        summary_only=frozenset({"asqi_thing"}),
    ).indicators[0]

    assert scored.level == "C"
    assert scored.ceiling_reason == "summary_only"


def test_worst_stratum_grades_the_weakest_cell_that_is_big_enough():
    scored = grade(
        card(
            {
                "source": "worst_stratum",
                "name": "correct",
                "pack_id": "procedural_ng",
                "min_n": 30,
            },
            [{"level": "A", "condition": "greater_equal", "threshold": 0.8}],
        ),
        bundle(
            rate("correct", 0.95, 0.9, 0.98, n=100, stratum={"language": "en"}),
            rate("correct", 0.60, 0.5, 0.70, n=100, stratum={"language": "pcm"}),
            rate("correct", 0.10, 0.01, 0.40, n=5, stratum={"language": "ha"}),
        ),
        "black_box",
    ).indicators[0]

    assert scored.measured[0].value == 0.60, "the n=5 cell is noise and must not be the worst"
    assert scored.measured[0].stratum == {"language": "pcm"}, (
        "a worst stratum that does not name the cell is not a finding"
    )
    assert scored.verdict == "ungraded"


def test_no_stratum_large_enough_is_an_error_rather_than_a_grade():
    with pytest.raises(ScoreCardError, match="reaches n=30"):
        grade(
            card(
                {"source": "worst_stratum", "name": "correct", "pack_id": "procedural_ng"},
                PASSES,
            ),
            bundle(rate("correct", 0.9, 0.8, 0.95, n=5, stratum={"language": "ha"})),
            "black_box",
        )


def test_a_level_no_rule_can_award_is_refused_by_the_contract():
    with pytest.raises(ValueError, match="not in `levels`"):
        ScoreCard(
            score_card_name="test",
            levels=LEVELS,
            indicators=[
                {
                    "id": "indicator",
                    "metric": {"name": "correct"},
                    "assessment": [{"level": "Z", "condition": "greater_equal", "threshold": 0.5}],
                }
            ],
        )


def coverage_bundle():
    """One metric, two stratum dimensions. The language cells are weaker than the
    geographic ones, so an indicator that cannot tell them apart returns the wrong cell."""
    return bundle(
        rate("covered", 0.60, 0.55, 0.65, n=500, stratum={"zone": "north"}),
        rate("covered", 0.70, 0.65, 0.75, n=500, stratum={"zone": "south"}),
        rate("covered", 0.20, 0.16, 0.25, n=400, stratum={"language": "pcm"}),
        rate("covered", 0.80, 0.76, 0.84, n=400, stratum={"language": "en"}),
    )


def worst_over(keys):
    return card(
        {"source": "worst_stratum", "name": "covered", "pack_id": "procedural_ng", "keys": keys},
        [{"level": "A", "condition": "greater_equal", "threshold": 0.9}],
    )


def test_a_worst_stratum_can_be_confined_to_one_stratum_key():
    """Two indicators over two dimensions have to be able to differ. Without this they
    search every cell carrying any stratum and return the same one."""
    geographic = grade(worst_over(["zone"]), coverage_bundle(), "black_box").indicators[0]
    language = grade(worst_over(["language"]), coverage_bundle(), "black_box").indicators[0]

    assert geographic.measured[0].stratum == {"zone": "north"}
    assert language.measured[0].stratum == {"language": "pcm"}
    assert geographic.measured[0].value != language.measured[0].value


def test_without_keys_every_cell_is_a_candidate():
    """The old behaviour, kept as the default so a card that does not care need not say so."""
    both = grade(worst_over([]), coverage_bundle(), "black_box").indicators[0]
    assert both.measured[0].stratum == {"language": "pcm"}


def test_a_key_no_cell_carries_is_an_error_naming_the_key():
    with pytest.raises(ScoreCardError, match="keyed by agency"):
        grade(worst_over(["agency"]), coverage_bundle(), "black_box")


NOT_HERE = {"name": "confidence_weighted", "pack_id": "procedural_ng"}


def tiered_card():
    """Assessable at grey box, and not a question black box can answer at all."""
    return ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        tier_ceilings={"black_box": "A", "grey_box": "A"},
        indicators=[
            {
                "id": "indicator",
                "metric": NOT_HERE,
                "assessment": PASSES,
                "tier_ceilings": {"black_box": None},
            }
        ],
    )


def test_an_indicator_unassessable_at_this_tier_is_ungraded_not_an_error():
    """The metric is never looked for. A black box bundle has no reason to hold it, and
    reporting that absence as a broken reference would blame the score card for a limit the
    score card is the thing describing."""
    scored = grade(tiered_card(), bundle(rate("correct", 0.9, 0.85, 0.93)), "black_box")

    assert scored.indicators[0].verdict == "ungraded"
    assert scored.indicators[0].level is None
    assert "black_box" in (scored.indicators[0].reason or "")


def test_check_skips_a_reference_that_tier_will_never_follow():
    assert check(tiered_card(), bundle(rate("correct", 0.9, 0.85, 0.93)), "black_box") == []


def test_the_same_reference_is_still_checked_at_a_tier_that_can_ask():
    problems = check(tiered_card(), bundle(rate("correct", 0.9, 0.85, 0.93)), "grey_box")
    assert any("confidence_weighted" in problem for problem in problems)


def test_an_indicator_ceiling_overrides_the_card_for_that_indicator_alone():
    scored = grade(
        ScoreCard(
            score_card_name="test",
            levels=LEVELS,
            tier_ceilings={"black_box": "A"},
            indicators=[
                {
                    "id": "capped",
                    "metric": {"name": "correct", "pack_id": "procedural_ng"},
                    "assessment": PASSES,
                    "tier_ceilings": {"black_box": "C"},
                },
                {
                    "id": "uncapped",
                    "metric": {"name": "correct", "pack_id": "procedural_ng"},
                    "assessment": PASSES,
                },
            ],
        ),
        bundle(rate("correct", 0.9, 0.85, 0.93)),
        "black_box",
    )

    assert scored.indicators[0].level == "C"
    assert scored.indicators[0].uncapped_level == "A"
    assert scored.indicators[1].level == "A", "the card level ceiling still applies elsewhere"
