"""Between-replicate variance. The fix for teardown section 3.2."""

import pytest

from touchstone.contracts import ItemRecord
from touchstone.stats.replicates import between_replicate


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
