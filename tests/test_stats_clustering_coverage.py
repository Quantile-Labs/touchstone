"""The simulation that found the defect, kept as the test that it stays fixed.

Scoring an item across several replicates does not give several independent observations
of the system. Counting the rows and handing that to a Wilson interval is wrong in the
dangerous direction: against the rate the system would show on items like these, a nominal
95 percent interval over 200 items at ten replicates holds about 67 percent of the time,
and at twenty replicates it holds about 54. The width shrinks with every replicate added
while the thing it is meant to cover does not move.

Against the rate on these exact items the same interval is too wide instead, near 98
percent. That is why the fix cannot simply be to widen everything: the two rates are
different quantities and the row count is the wrong denominator for both.

Seeded, so a failure here is a change in the arithmetic rather than a bad afternoon.
"""

import random
from statistics import fmean, variance

import pytest

from touchstone.stats.proportion import clustered_wilson, wilson

SUPERPOPULATION = (0.10, 0.25, 0.40, 0.55, 0.70, 0.85, 0.95)
"""Item difficulties an item is drawn from. Spread on purpose: the defect is invisible
when every item is equally hard, because then the rows really are exchangeable."""

TRUE_RATE = fmean(SUPERPOPULATION)
ITEMS = 200
TRIALS = 1500


def _coverage(replicates: int, seed: int = 5) -> tuple[float, float, float]:
    """Coverage of the naive and the clustered interval, and the naive interval's width."""
    rng = random.Random(seed)
    naive = clustered = 0
    width = 0.0
    for _ in range(TRIALS):
        cells = []
        for _ in range(ITEMS):
            rate = rng.choice(SUPERPOPULATION)
            cells.append((sum(1 for _ in range(replicates) if rng.random() < rate), replicates))

        k = sum(successes for successes, _ in cells)
        n = sum(observations for _, observations in cells)
        _, low, high = wilson(k, n)
        naive += low <= TRUE_RATE <= high
        width += high - low

        computed = clustered_wilson(cells)
        clustered += computed.low <= TRUE_RATE <= computed.high
    return naive / TRIALS, clustered / TRIALS, width / TRIALS


def test_counting_rows_collapses_the_coverage_as_replicates_are_added():
    """The defect. One replicate is fine, and every one after it makes the claim worse."""
    one, _, _ = _coverage(1)
    assert one > 0.93, "a single replicate per item is not clustered and should cover"

    previous = one
    for replicates in (2, 5, 10, 20):
        naive, _, _ = _coverage(replicates)
        assert naive < previous, f"{replicates} replicates covered {naive:.1%}, no worse than fewer"
        previous = naive
    assert previous < 0.65, f"twenty replicates should collapse the coverage, got {previous:.1%}"


def test_the_naive_interval_narrows_while_the_truth_stays_put():
    """Why it reads as precision. The interval buys width from replicates it has not earned."""
    _, _, one = _coverage(1)
    _, _, twenty = _coverage(20)
    assert twenty < one / 3, f"width went {one:.4f} to {twenty:.4f}, less shrinkage than expected"


def test_the_clustered_interval_holds_its_nominal_coverage():
    """Around 94 to 96 percent at every replicate count, which is the whole fix.

    The bar is 93 rather than 95 for the same reason the worst-stratum test uses 93:
    Wilson's own coverage oscillates with the discreteness of the counts before any
    correction is involved, and that floor is inherited rather than introduced.
    """
    for replicates in (1, 2, 5, 10, 20):
        _, clustered, _ = _coverage(replicates)
        assert clustered >= 0.93, f"{replicates} replicates covered {clustered:.1%}"


def test_the_correction_does_nothing_when_there_is_nothing_to_correct():
    """One observation per item is the unclustered case and has to come back unchanged."""
    rng = random.Random(3)
    cells = [(1 if rng.random() < 0.7 else 0, 1) for _ in range(ITEMS)]
    k = sum(successes for successes, _ in cells)

    point, low, high = wilson(k, ITEMS)
    computed = clustered_wilson(cells)
    assert computed.point == point
    assert computed.effective_n == float(ITEMS)
    assert (computed.low, computed.high) == (low, high)


def test_replicates_that_never_disagree_are_worth_one_observation_each():
    """Sixty items right ten times out of ten is sixty observations, not six hundred.

    The degenerate case that motivates the lower clamp. Pooling the rows would report an
    interval on 600 trials, which is a far stronger claim than the evidence supports and
    is the shape of the error a reader is least able to catch.
    """
    cells = [(10, 10)] * 60
    computed = clustered_wilson(cells)
    _, floor_low, _ = wilson(60, 60)
    _, pooled_low, _ = wilson(600, 600)

    assert computed.point == 1.0
    assert computed.effective_n == 60.0
    assert computed.low == floor_low
    assert computed.low < pooled_low


def test_the_effective_size_stays_between_the_items_and_the_rows():
    """Perfect agreement at one end of the scale, no correlation at the other."""
    rng = random.Random(17)
    for replicates in (2, 4, 8):
        for rate in (0.05, 0.3, 0.5, 0.9):
            cells = [
                (sum(1 for _ in range(replicates) if rng.random() < rate), replicates)
                for _ in range(80)
            ]
            computed = clustered_wilson(cells)
            assert 80.0 <= computed.effective_n <= float(80 * replicates)
            assert computed.design_effect >= 1.0 - 1e-12


def _drawn(replicates, items=ITEMS, seed=11):
    """One draw of `items` cells, difficulties spread, so the between-item term is real."""
    rng = random.Random(seed)
    cells = []
    for _ in range(items):
        rate = rng.choice(SUPERPOPULATION)
        cells.append((sum(1 for _ in range(replicates) if rng.random() < rate), replicates))
    return cells


def _naive_variance(cells):
    """The A.3.1 calculation: the sample variance over every row, over the row count.

    Built out of the rows themselves rather than reduced to `p (1 - p) / (n t)`, so what
    the tests below reject is the calculation the report names rather than an algebraic
    stand-in a later reader would have to check for themselves.
    """
    rows = [
        float(hit)
        for successes, observations in cells
        for hit in [1] * successes + [0] * (observations - successes)
    ]
    return variance(rows) / len(rows)


def _benchmark_variance(cells):
    """`sum_i z_i (1 - z_i) / (n^2 (t - 1))`, the within-item term carried by itself."""
    items = len(cells)
    return sum((k / t) * (1 - k / t) / (items * items * (t - 1)) for k, t in cells if t > 1)


def _shipped_variance(computed):
    """The variance the reported interval rests on, read back off the effective size."""
    return computed.point * (1 - computed.point) / computed.effective_n


def test_the_interval_reports_generalized_accuracy_and_not_the_row_count():
    """`Var[Z_i] / n` over items, which is the estimand a score card grades against.

    NIST AI 800-3 Appendix A.3.1 gives the row-counting standard error a name and a
    section of its own, and this is the regression test that it does not come back. The
    identity is exact rather than approximate because the effective size is defined as
    the one at which a Wilson interval carries that variance, so a change anywhere in the
    denominator moves it. Both clamps are asserted to be off first, since a clamped
    effective size is a different arithmetic and would pass the comparison for the wrong
    reason.
    """
    cells = _drawn(4)
    computed = clustered_wilson(cells)
    scores = [k / t for k, t in cells]
    rows = sum(t for _, t in cells)

    assert len(cells) < computed.effective_n < rows, "clamped, so the identity is untested"
    assert _shipped_variance(computed) == pytest.approx(variance(scores) / len(cells), rel=1e-12)

    _, low, high = wilson(sum(k for k, _ in cells), rows)
    assert _naive_variance(cells) < _shipped_variance(computed)
    assert (computed.high - computed.low) > (high - low)


def test_the_narrower_benchmark_accuracy_estimand_is_not_the_one_reported():
    """The other correct estimand, and the reason it is not the one on offer here.

    Benchmark accuracy is the rate on this fixed list of items, so its variance carries
    the within-item term alone and is narrower wherever the items differ in difficulty.
    Narrower is not better: a score card grades a system against a threshold, and the
    reader relying on that grade is meeting items nobody has seen, so the estimand has to
    be the one whose variance admits that the list was itself a sample.
    """
    cells = _drawn(4)
    computed = clustered_wilson(cells)

    assert _benchmark_variance(cells) < _shipped_variance(computed)
