"""Between-replicate variance. The fix for teardown section 3.2."""

import random
from statistics import fmean

import pytest

from touchstone.contracts import ItemRecord
from touchstone.stats.replicates import between_replicate, variance_components


def _item(item_id, replicate, correct):
    return ItemRecord(item_id=item_id, replicate=replicate, outcome={"correct": correct})


def test_a_deterministic_system_reports_no_spread_and_no_churn():
    items = [_item(f"q{i}", r, i < 6) for r in (0, 1) for i in range(10)]
    spread = between_replicate(items, "correct")
    assert spread.rates == {0: (6, 10), 1: (6, 10)}
    assert spread.sd == 0.0
    assert spread.spread == 0.0
    assert (spread.unstable_items, spread.repeated_items) == (0, 10)


def test_a_steady_rate_can_still_hide_a_system_disagreeing_with_itself():
    """The two numbers are not derivable from each other, which is why both are reported."""
    items = [_item(f"q{i}", 0, i < 5) for i in range(10)]
    items += [_item(f"q{i}", 1, i >= 5) for i in range(10)]
    spread = between_replicate(items, "correct")
    assert spread.spread == 0.0
    assert (spread.unstable_items, spread.repeated_items) == (10, 10)


def test_a_drifting_rate_is_reported_as_spread():
    items = [_item(f"q{i}", 0, i < 4) for i in range(10)]
    items += [_item(f"q{i}", 1, i < 8) for i in range(10)]
    spread = between_replicate(items, "correct")
    assert spread.rates == {0: (4, 10), 1: (8, 10)}
    assert spread.mean == pytest.approx(0.6)
    assert spread.spread == 0.4


def test_one_replicate_cannot_report_its_own_stability():
    spread = between_replicate([_item("q0", 0, True)], "correct")
    assert spread.sd is None
    assert spread.spread == 0.0
    assert spread.repeated_items == 0


def test_an_item_seen_once_is_not_in_the_churn_denominator():
    items = [_item("both", 0, True), _item("both", 1, False), _item("once", 0, True)]
    spread = between_replicate(items, "correct")
    assert (spread.unstable_items, spread.repeated_items) == (1, 1)


def test_the_two_components_add_up_to_the_reported_total():
    parts = variance_components([(k, 4) for k in (0, 1, 2, 3, 4, 2, 1, 3)])
    assert parts is not None
    assert parts.completion + parts.item == pytest.approx(parts.total)
    assert parts.items == 8
    assert parts.trials == 4.0


def test_the_completion_term_is_recovered_on_items_of_known_difficulty():
    """Every item at Pi = 0.5, so Var[Pi] is zero and the whole variance is completion.

    A binomial at 0.5 over 4 trials gives E[Pi(1-Pi)]/t = 0.25/4 = 0.0625, and the item
    term should floor at or near zero rather than absorbing the completion noise.
    """
    rng = random.Random(11)
    trials = 4
    cells = [(sum(rng.random() < 0.5 for _ in range(trials)), trials) for _ in range(4000)]
    parts = variance_components(cells)
    assert parts is not None
    assert parts.completion == pytest.approx(0.0625, abs=0.002)
    assert parts.item == pytest.approx(0.0, abs=0.002)


def test_the_item_term_is_recovered_when_items_differ_in_difficulty():
    """Half the items at Pi = 0.2 and half at Pi = 0.8.

    Var[Pi] = 0.09 exactly, and E[Pi(1-Pi)]/t = 0.16/4 = 0.04. The estimator has to put
    the mass in the right two places, because that is the whole claim being made.
    """
    rng = random.Random(23)
    trials = 4
    cells = []
    for index in range(4000):
        probability = 0.2 if index % 2 else 0.8
        cells.append((sum(rng.random() < probability for _ in range(trials)), trials))
    parts = variance_components(cells)
    assert parts is not None
    assert parts.completion == pytest.approx(0.04, abs=0.002)
    assert parts.item == pytest.approx(0.09, abs=0.004)


def test_the_naive_within_item_form_understates_the_completion_term():
    """The `t - 1` in the pooled estimator is the difference, and at two trials it doubles.

    A mean of `z(1 - z)` over items divided by `t` is the form that reads correct and is
    not: E[z(1-z)] = Pi(1-Pi)(t-1)/t, so the shortfall is handed to the item term.
    """
    cells = [(1, 2)] * 100
    parts = variance_components(cells)
    assert parts is not None
    naive = fmean((k / t) * (1 - k / t) for k, t in cells) / 2
    assert naive == pytest.approx(0.125)
    assert parts.completion == pytest.approx(0.25)


def test_an_unbalanced_grid_keeps_the_item_a_replicate_lost():
    """Pooling over `sum(t_i - 1)` rather than `n (t - 1)` is what makes this work."""
    parts = variance_components([(1, 2), (2, 4), (2, 3)])
    assert parts is not None
    assert parts.items == 3
    assert parts.trials == pytest.approx(3.0)
    assert parts.completion == pytest.approx((0.5 + 1.0 + 2 / 3) / 6 / 3)


def test_the_split_is_refused_where_it_is_not_identifiable():
    assert variance_components([]) is None
    assert variance_components([(1, 4)]) is None, "one item has no between-item variance"
    assert variance_components([(1, 1), (0, 1)]) is None, "one trial cannot see completion noise"


def test_a_negative_moment_estimate_is_floored_rather_than_reported():
    """Items agreeing more than binomial sampling allows drive the moment estimate below
    zero, and a negative variance is not a number to put in a bundle."""
    parts = variance_components([(2, 4)] * 40)
    assert parts is not None
    assert parts.item == 0.0
    assert parts.total == parts.completion


def test_the_split_travels_on_the_replicate_variance_record():
    items = [_item(f"q{i}", r, i < 6) for r in (0, 1) for i in range(10)]
    spread = between_replicate(items, "correct")
    assert spread.components is not None
    assert spread.components.items == 10
    assert spread.components.trials == 2.0
    assert spread.components.completion == 0.0, "a deterministic system has no completion noise"


def test_a_single_replicate_carries_no_split():
    items = [_item(f"q{i}", 0, i < 6) for i in range(10)]
    assert between_replicate(items, "correct").components is None


def test_counts_that_are_not_counts_are_refused():
    with pytest.raises(ValueError):
        variance_components([(1, 0)])
    with pytest.raises(ValueError):
        variance_components([(3, 2)])
