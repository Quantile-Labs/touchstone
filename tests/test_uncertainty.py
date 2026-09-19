"""The uncertainty budget, the replicate homogeneity test, and the recorded assumptions."""

from math import erfc

import pytest

from touchstone.contracts import ItemRecord
from touchstone.estimate import estimate
from touchstone.stats.proportion import Z_95
from touchstone.stats.replicates import chi_square_sf, homogeneity
from touchstone.uncertainty import UNQUANTIFIED


def _rows(rates, items=100):
    """`rates[r]` of `items` answered correctly in replicate `r`, over the same items."""
    return [
        ItemRecord(item_id=f"q{i}", replicate=r, outcome={"correct": i < round(rate * items)})
        for r, rate in enumerate(rates)
        for i in range(items)
    ]


def _single(items=50, correct=40):
    return [ItemRecord(item_id=f"q{i}", outcome={"correct": i < correct}) for i in range(items)]


@pytest.mark.parametrize(
    ("critical", "df"),
    [(3.841459, 1), (5.991465, 2), (7.814728, 3), (9.487729, 4), (11.070498, 5)],
)
def test_the_survival_function_puts_five_percent_past_each_critical_value(critical, df):
    assert chi_square_sf(critical, df) == pytest.approx(0.05, abs=1e-6)


def test_homogeneity_matches_the_two_by_two_table_by_hand():
    """40 of 100 against 60 of 100: pooled 0.5, each cell 10 off an expected 50."""
    statistic, df, p_value = homogeneity({0: (40, 100), 1: (60, 100)})
    assert (statistic, df) == (pytest.approx(8.0), 1)
    assert p_value == pytest.approx(erfc(2.0))


def test_homogeneity_needs_two_replicates_and_holds_at_a_rate_of_one():
    assert homogeneity({0: (5, 10)}) is None
    assert homogeneity({0: (10, 10), 1: (10, 10)}) == (0.0, 1, 1.0)


def test_every_whole_sample_figure_carries_a_budget_naming_what_is_not_quantified():
    computed = estimate(_single())
    whole = [entry for entry in computed.estimates if not entry.stratum]

    assert [(b.metric, b.pack_id) for b in computed.uncertainty] == [
        (entry.metric, entry.pack_id) for entry in whole
    ]
    for budget in computed.uncertainty:
        unsized = [p.source for p in budget.components if p.magnitude == "unquantified"]
        assert unsized == [source for source, _ in UNQUANTIFIED]


def test_a_single_run_sizes_sampling_from_the_interval_it_stores():
    computed = estimate(_single())
    figure = computed.estimates[0]
    (sampling,) = [p for p in computed.uncertainty[0].components if p.source == "sampling"]

    assert sampling.magnitude == pytest.approx((figure.high - figure.low) / (2 * Z_95))
    assert sampling.reference == figure.reference


def test_a_rate_of_zero_still_carries_sampling_uncertainty():
    """The normal standard error reads zero here. The Wilson interval does not."""
    computed = estimate(_single(correct=0))
    (sampling,) = [p for p in computed.uncertainty[0].components if p.source == "sampling"]
    assert sampling.magnitude > 0


def test_replicates_split_sampling_into_its_completion_and_item_parts():
    computed = estimate(_rows([0.5, 0.5]))
    parts = computed.replicate_variance[0].components
    sized = {
        p.source: p.magnitude
        for p in computed.uncertainty[0].components
        if p.magnitude != "unquantified"
    }

    assert sized == {
        "completion_sampling": pytest.approx((parts.completion / parts.items) ** 0.5),
        "item_sampling": pytest.approx((parts.item / parts.items) ** 0.5),
    }


def test_one_replicate_leaves_the_functional_form_unchecked():
    names = {a.name: a.result for a in estimate(_single()).assumptions}
    assert names == {
        "unidimensional": "not checked",
        "functional_form": "not checked",
        "independent_items": "not checked",
    }


def test_steady_replicates_are_consistent_with_one_probability_per_item():
    (checked,) = [a for a in estimate(_rows([0.6, 0.6])).assumptions if a.metric]
    assert (checked.name, checked.result) == ("functional_form", "consistent")
    assert checked.parameters["p_value"] == 1.0


def test_a_system_that_drifted_between_replicates_violates_it():
    (checked,) = [a for a in estimate(_rows([0.4, 0.6])).assumptions if a.metric]
    assert checked.result == "violated"
    assert "0.400, 0.600" in checked.finding


def test_pooling_packs_is_named_against_unidimensionality():
    items = [row.model_copy(update={"pack_id": "a"}) for row in _single()]
    items += [
        row.model_copy(update={"pack_id": "b", "item_id": f"b{row.item_id}"}) for row in _single()
    ]
    (assumed,) = [a for a in estimate(items).assumptions if a.name == "unidimensional"]
    assert "pool 2 packs" in assumed.finding
