"""Wilson, and the formatter that cannot print a bare rate."""

import doctest
from math import isnan

import pytest

from touchstone.stats import proportion
from touchstone.stats.proportion import format_rate, wilson


def test_matches_the_published_interval():
    """QL-2026-01 05-results/primary.json, rung_2_real_gauges. See
    tests/test_estimate_credential.py for what this number is."""
    assert wilson(242, 3090) == (
        0.07831715210355987,
        0.06935898244776396,
        0.0883225226428651,
    )


def test_interval_brackets_the_point_estimate():
    point, low, high = wilson(7, 40)
    assert low < point < high


def test_interval_stays_inside_the_unit_interval_at_the_extremes():
    """Where the normal approximation goes negative, which is the reason for Wilson."""
    _, low, high = wilson(0, 10)
    assert low == 0.0
    assert 0.0 < high < 1.0

    _, low, high = wilson(10, 10)
    assert high == 1.0
    assert 0.0 < low < 1.0


def test_interval_narrows_as_the_denominator_grows():
    _, small_low, small_high = wilson(5, 10)
    _, large_low, large_high = wilson(500, 1000)
    assert (large_high - large_low) < (small_high - small_low)


def test_no_observations_is_not_a_rate_of_zero():
    point, low, high = wilson(0, 0)
    assert isnan(point)
    assert (low, high) == (0.0, 1.0)
    assert format_rate(0, 0) == "undefined (n=0)"


@pytest.mark.parametrize(("k", "n"), [(-1, 10), (5, -1), (11, 10)])
def test_impossible_counts_are_refused(k, n):
    with pytest.raises(ValueError):
        wilson(k, n)


def test_format_carries_point_interval_and_denominator():
    assert format_rate(242, 3090) == "7.8% (95% CI 6.9-8.8%, n=3090)"
    assert format_rate(242, 3090, dp=2) == "7.83% (95% CI 6.94-8.83%, n=3090)"


def test_the_docstring_examples_run():
    """The rule from CONTEXT.md section 6: prose describing behaviour has a test."""
    results = doctest.testmod(proportion)
    assert results.failed == 0
