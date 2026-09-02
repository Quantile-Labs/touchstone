"""The rollup, the worst-stratum guard, and reading item records off disk."""

import json

import pytest
from typer.testing import CliRunner

from touchstone.cli import app
from touchstone.contracts import ItemRecord
from touchstone.errors import EstimateError
from touchstone.estimate import (
    ESTIMATES_NAME,
    estimate,
    load_items,
    worst_stratum,
    write_estimates,
)
from touchstone.stats.bootstrap import bootstrap_bca


def _items(n=100, thin=3):
    """Two fat cells and one deliberately thin one."""
    items = [
        ItemRecord(
            item_id=f"q{index}",
            stratum={"language": "a" if index < 50 else "b", "task": "t"},
            outcome={"correct": index % 4 != 0},
            score={"rubric": float(index % 5)},
        )
        for index in range(n)
    ]
    items += [
        ItemRecord(
            item_id=f"thin{index}",
            stratum={"language": "c", "task": "t"},
            outcome={"correct": False},
            score={"rubric": 0.0},
        )
        for index in range(thin)
    ]
    return items


def _by_cell(estimates, metric):
    return {
        tuple(sorted(entry.stratum.items())): entry
        for entry in estimates.estimates
        if entry.metric == metric
    }


def test_every_cell_carries_its_denominator():
    cells = _by_cell(estimate(_items(), ["language"]), "correct")
    assert cells[()].n == 103
    assert cells[(("language", "a"),)].n == 50
    assert cells[(("language", "c"),)].n == 3


def test_crossing_two_keys_gives_the_product_of_the_cells():
    cells = _by_cell(estimate(_items(), ["language", "task"]), "correct")
    assert (("language", "a"), ("task", "t")) in cells


def test_several_keys_are_rolled_up_one_at_a_time_as_well_as_crossed():
    """A card asks about one dimension per indicator. Crossing every key it was given and
    stopping there leaves those indicators with no cell to read, and `grade` then refuses a
    metric that was never computed."""
    cells = _by_cell(estimate(_items(), ["language", "task"]), "correct")

    assert cells[(("language", "a"),)].n == 50
    assert cells[(("task", "t"),)].n == 103
    assert cells[(("language", "a"), ("task", "t"))].n == 50


def test_a_single_key_is_not_rolled_up_twice():
    """One key crossed with nothing is that key on its own, so it is emitted once."""
    entries = [
        entry
        for entry in estimate(_items(), ["language"]).estimates
        if entry.metric == "correct" and entry.stratum == {"language": "a"}
    ]
    assert len(entries) == 1


def test_an_item_missing_a_requested_key_is_marked_rather_than_dropped():
    """Dropping it would silently shrink the denominator."""
    items = [
        ItemRecord(item_id="has", stratum={"language": "a"}, outcome={"correct": True}),
        ItemRecord(item_id="lacks", outcome={"correct": True}),
    ]
    cells = _by_cell(estimate(items, ["language"]), "correct")
    assert cells[(("language", "(unset)"),)].n == 1
    assert cells[()].n == 2


def test_an_outcome_a_pack_never_reported_is_in_no_denominator():
    items = [
        ItemRecord(item_id="a", outcome={"correct": True, "refused": False}),
        ItemRecord(item_id="b", outcome={"correct": False}),
    ]
    cells = _by_cell(estimate(items), "refused")
    assert cells[()].n == 1


def test_a_continuous_score_gets_a_bootstrap_interval_and_no_numerator():
    entry = _by_cell(estimate(_items(), ["language"]), "rubric")[()]
    assert entry.k is None
    assert entry.estimator == "bootstrap_bca"
    assert entry.low < entry.point < entry.high


def test_a_repeated_score_is_bootstrapped_over_items_rather_than_rows():
    """The continuous half of the clustering defect, guarded at the caller.

    The bootstrap resamples whatever sample it is handed, so handing it the rows would
    draw the same item's score again as though the second draw were new evidence, which
    is the standard error NIST AI 800-3 Appendix A.3.1 names computed by a different
    route. Forty items scored three times each are forty observations, and the interval
    the run reports is accordingly about the square root of three wider than the one the
    rows would have bought.
    """
    items = [
        ItemRecord(item_id=f"q{index}", score={"rubric": float(index % 5)}, replicate=replicate)
        for index in range(40)
        for replicate in range(3)
    ]
    entry = _by_cell(estimate(items, seed=7), "rubric")[()]
    _, low, high = bootstrap_bca([item.score["rubric"] for item in items], seed=7)

    assert entry.n == 120
    assert entry.parameters["items"] == 40
    assert entry.parameters["effective_n"] == 40.0
    assert (entry.high - entry.low) > 1.5 * (high - low)


def test_estimates_are_reproducible_from_the_same_records_and_seed():
    items = _items()
    assert estimate(items, ["language"], seed=4).model_dump() == (
        estimate(items, ["language"], seed=4).model_dump()
    )


def test_worst_stratum_ignores_a_cell_below_the_minimum_size():
    """The min_n guard is what stops a three-item cell becoming a headline."""
    found = worst_stratum(estimate(_items(), ["language"]), "correct", min_n=30)
    assert found.worst.stratum == {"language": "a"}
    assert [entry.stratum for entry in found.excluded] == [{"language": "c"}]


def test_the_thin_cell_wins_once_the_guard_is_lowered():
    found = worst_stratum(estimate(_items(), ["language"]), "correct", min_n=3)
    assert found.worst.stratum == {"language": "c"}
    assert found.excluded == []


def test_no_cell_reaching_the_minimum_is_a_finding_not_a_missing_value():
    found = worst_stratum(estimate(_items(), ["language"]), "correct", min_n=500)
    assert found.worst is None
    assert len(found.excluded) == 3


def test_worst_stratum_can_be_asked_which_direction_is_bad():
    estimates = estimate(_items(), ["language"])
    higher = worst_stratum(estimates, "correct", min_n=3, higher_is_better=True)
    lower = worst_stratum(estimates, "correct", min_n=3, higher_is_better=False)
    assert higher.worst.stratum != lower.worst.stratum


def test_worst_stratum_refuses_a_minimum_below_one():
    with pytest.raises(EstimateError):
        worst_stratum(estimate(_items(), ["language"]), "correct", min_n=0)


def test_calibration_is_computed_only_when_it_is_asked_for():
    """An ECE against an unrelated boolean reads as authoritative and means nothing."""
    items = [
        ItemRecord(item_id=f"q{index}", confidence=0.9, outcome={"correct": True, "refused": False})
        for index in range(10)
    ]
    assert estimate(items).calibration == []
    named = estimate(items, calibrate=["correct"])
    assert [curve.metric for curve in named.calibration] == ["correct"]


def test_calibrating_an_outcome_no_item_reports_is_refused():
    items = [ItemRecord(item_id="a", confidence=0.9, outcome={"correct": True})]
    with pytest.raises(EstimateError, match="no item reports it"):
        estimate(items, calibrate=["accuracy"])


def test_calibrating_an_outcome_with_no_confidence_is_refused():
    items = [ItemRecord(item_id="a", outcome={"correct": True})]
    with pytest.raises(EstimateError, match="no item carrying it reports a confidence"):
        estimate(items, calibrate=["correct"])


def test_replicate_variance_appears_only_where_there_is_more_than_one_replicate():
    single = [ItemRecord(item_id="a", outcome={"correct": True})]
    assert estimate(single).replicate_variance == []

    repeated = single + [ItemRecord(item_id="a", replicate=1, outcome={"correct": False})]
    assert [spread.metric for spread in estimate(repeated).replicate_variance] == ["correct"]


def test_missing_item_records_name_the_path(tmp_path):
    with pytest.raises(EstimateError, match="no item records"):
        load_items(tmp_path)


def test_a_malformed_line_names_its_line_number(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text('{"item_id": "a"}\n{"item_id": ""}\n')
    with pytest.raises(EstimateError, match="items.jsonl:2"):
        load_items(path)


def test_an_empty_file_is_refused(tmp_path):
    (tmp_path / "items.jsonl").write_text("\n\n")
    with pytest.raises(EstimateError, match="holds no item records"):
        load_items(tmp_path)


def test_written_estimates_load_back(tmp_path):
    estimates = estimate(_items(), ["language"])
    path = write_estimates(estimates, tmp_path)
    assert path.name == ESTIMATES_NAME
    assert json.loads(path.read_text())["items"] == 103


def test_the_cli_refuses_a_directory_holding_no_records(tmp_path):
    result = CliRunner().invoke(app, ["estimate", str(tmp_path)])
    assert result.exit_code == 1
    assert "no item records" in result.output


def test_the_cli_prints_no_rate_without_its_interval(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text(
        "".join(json.dumps(item.model_dump(), sort_keys=True) + "\n" for item in _items(20, thin=0))
    )
    result = CliRunner().invoke(app, ["estimate", str(tmp_path), "--by", "language"])
    assert result.exit_code == 0, result.output
    for line in result.output.splitlines():
        if "correct [" in line:
            assert "95% CI" in line and "n=" in line


def test_the_worst_cell_carries_an_interval_widened_for_the_selection():
    """The winner of a ranking is not a cell somebody picked in advance."""
    estimates = estimate(_items(), ["language"])
    found = worst_stratum(estimates, "correct", min_n=30)
    marginal = next(
        entry
        for entry in estimates.estimates
        if entry.metric == "correct" and entry.stratum == found.worst.stratum
    )

    assert found.selected_from == 2
    assert found.worst.point == marginal.point
    assert found.worst.low < marginal.low
    assert found.worst.high > marginal.high
    assert found.worst.parameters["adjustment"] == "bonferroni"
    assert found.worst.parameters["selected_from"] == 2


def test_one_eligible_cell_is_not_a_selection_and_is_not_widened():
    items = [
        ItemRecord(
            item_id=f"q{index}", stratum={"language": "a"}, outcome={"correct": index % 4 != 0}
        )
        for index in range(40)
    ] + [
        ItemRecord(item_id=f"thin{index}", stratum={"language": "c"}, outcome={"correct": False})
        for index in range(3)
    ]
    estimates = estimate(items, ["language"])
    found = worst_stratum(estimates, "correct", min_n=30)
    marginal = next(
        entry
        for entry in estimates.estimates
        if entry.metric == "correct" and entry.stratum == found.worst.stratum
    )

    assert found.selected_from == 1
    assert (found.worst.low, found.worst.high) == (marginal.low, marginal.high)


def test_a_worst_cell_without_counts_is_refused_rather_than_reported():
    """A selected minimum printed with an unadjusted interval is the whole defect."""
    estimates = estimate(_items(), ["language"])
    stripped = estimates.model_copy(
        update={
            "estimates": [
                entry.model_copy(update={"k": None})
                if entry.metric == "correct"
                else entry.model_copy()
                for entry in estimates.estimates
            ]
        }
    )
    with pytest.raises(EstimateError, match="carries no counts"):
        worst_stratum(stripped, "correct", min_n=30)
