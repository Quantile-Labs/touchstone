"""The paired difference, and the unpaired one it falls back to.

The paired interval is checked by hand against Miller's equation 7 and by simulation for
coverage. The unpaired one is checked against a worked pair of Wilson intervals and against
the paired one on correlated data, where it has to come out wider.
"""

import random
from math import sqrt
from statistics import fmean, stdev

import pytest

from touchstone.stats.paired import paired_difference, unpaired_difference
from touchstone.stats.proportion import Z_95, wilson


def test_equation_seven_by_hand():
    pairs = [(1.0, 0.0), (1.0, 1.0), (0.0, 0.0), (1.0, 0.0)]
    found = paired_difference(pairs)

    error = sqrt((4 * 0.25 / 3) / 4)
    assert found.point == pytest.approx(0.5)
    assert found.standard_error == pytest.approx(error)
    assert (found.low, found.high) == pytest.approx((0.5 - Z_95 * error, 0.5 + Z_95 * error))
    assert found.items == 4


def test_replicates_are_averaged_before_the_difference_is_taken():
    """An item scored at two of three replicates is 2/3, and it is one difference."""
    found = paired_difference([(2 / 3, 1 / 3), (1.0, 1.0), (0.0, 1 / 3)])
    assert found.items == 3
    assert found.point == pytest.approx(fmean([1 / 3, 0.0, -1 / 3]))


def test_a_bounded_interval_stays_inside_the_range_a_difference_of_rates_can_take():
    pairs = [(1.0, 0.0)] * 9 + [(0.0, 1.0)]
    assert paired_difference(pairs).high > 1.0
    assert paired_difference(pairs, bounded=True).high == 1.0


def test_one_item_is_refused():
    with pytest.raises(ValueError, match="at least two"):
        paired_difference([(1.0, 0.0)])


def test_the_unpaired_difference_of_two_wilson_intervals():
    """56/70 against 48/80, worked by hand from the two Wilson intervals."""
    now, before = wilson(56, 70), wilson(48, 80)
    point, low, high = unpaired_difference(now, before)

    assert point == pytest.approx(0.2)
    assert low == pytest.approx(0.0524, abs=5e-5)
    assert high == pytest.approx(0.3339, abs=5e-5)


def test_symmetric_intervals_add_in_quadrature():
    point, low, high = unpaired_difference((0.5, 0.4, 0.6), (0.3, 0.27, 0.33))
    half = sqrt(0.1**2 + 0.03**2)
    assert (point, low, high) == pytest.approx((0.2, 0.2 - half, 0.2 + half))


def simulated(rng, items, shift):
    """Two runs over the same items. Each item has one difficulty, and the second system
    is `shift` better on every item, so the runs agree about which items are hard."""
    pairs = []
    for _ in range(items):
        p = rng.random()
        pairs.append((float(rng.random() < min(1.0, p + shift)), float(rng.random() < p)))
    return pairs


def test_the_paired_interval_covers_the_change_at_its_nominal_rate():
    """Difficulty uniform on [0, 1] and a shift of s puts the true change at s - s^2 / 2,
    since items already near one cannot rise by the whole shift."""
    rng = random.Random(20260911)
    shift, trials = 0.05, 2000
    truth = shift - shift**2 / 2

    covered = 0
    for _ in range(trials):
        found = paired_difference(simulated(rng, 100, shift))
        covered += found.low <= truth <= found.high
    assert 0.93 <= covered / trials <= 0.97


def test_pairing_is_narrower_than_the_fallback_when_the_runs_agree_about_difficulty():
    rng = random.Random(7)
    pairs = simulated(rng, 400, 0.05)
    now = [one for one, _ in pairs]
    before = [two for _, two in pairs]

    def bounds(sample):
        k = int(sum(sample))
        return wilson(k, len(sample))

    _, low, high = unpaired_difference(bounds(now), bounds(before))
    found = paired_difference(pairs)

    assert found.high - found.low < high - low
    assert stdev([a - b for a, b in pairs]) > 0
