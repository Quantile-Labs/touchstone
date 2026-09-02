# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Proportions, with the interval attached.

The house rule is that no bare proportion leaves the laboratory, so the formatter here
takes the counts rather than a rate: there is no way to hand it a number that has already
lost its denominator.
"""

from collections.abc import Sequence
from math import nan, sqrt
from statistics import NormalDist, fmean, variance
from typing import NamedTuple

Z_95 = 1.96
"""Two-sided normal quantile for 95 percent. The only interval this tool prints."""

WILSON_REFERENCE = (
    "Wilson, E. B. (1927). Probable inference, the law of succession, and statistical "
    "inference. Journal of the American Statistical Association 22(158), 209-212."
)

BONFERRONI_REFERENCE = (
    "Miller, R. G. (1981). Simultaneous Statistical Inference, 2nd edition. Springer, "
    "chapter 1. The Bonferroni inequality applied to k simultaneous intervals."
)

CLUSTERED_REFERENCE = (
    "Kish, L. (1965). Survey Sampling. Wiley, section 8.2. The design effect, and the "
    "effective sample size a clustered design is worth."
)


def bonferroni_z(comparisons: int, confidence: float = 0.95) -> float:
    """The normal quantile for `confidence` held simultaneously over `comparisons` cells.

    One comparison returns `Z_95` rather than the exact 1.959964, so a rollup with a
    single eligible cell prints the same arithmetic as everywhere else in the tool and a
    reader is not asked to account for a difference in the sixth decimal that means
    nothing.
    """
    if comparisons < 1:
        raise ValueError(f"cannot adjust for {comparisons} comparisons")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence has to lie in (0, 1), got {confidence}")
    if comparisons == 1 and confidence == 0.95:
        return Z_95
    return NormalDist().inv_cdf(1 - (1 - confidence) / (2 * comparisons))


def interval(p: float, n: float, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score bounds for a rate `p` observed over `n` independent units.

    Split out from `wilson` because `clustered_wilson` needs the same arithmetic at an
    effective sample size that is not a whole number of anything. One definition, so a
    correction cannot drift away from the interval it corrects.
    """
    if n <= 0:
        return 0.0, 1.0
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson(k: int, n: int, z: float = Z_95) -> tuple[float, float, float]:
    """Wilson score interval for a proportion. Returns (point, low, high).

    Correct where the normal approximation breaks, which is wherever counts are small or
    the rate is near zero or one, and both happen in every stratified rollup. n == 0
    gives (nan, 0.0, 1.0): no observations is not the same as a rate of zero.

    `n` here is a count of *independent* observations. Where the same item was scored
    more than once, the rows are not independent and this is the wrong function: see
    `clustered_wilson`.
    """
    if n < 0 or k < 0:
        raise ValueError(f"counts cannot be negative: k={k}, n={n}")
    if k > n:
        raise ValueError(f"more successes than observations: k={k}, n={n}")
    if n == 0:
        return nan, 0.0, 1.0

    p = k / n
    low, high = interval(p, n, z)
    return p, low, high


class ClusteredProportion(NamedTuple):
    """A rate over repeated observations of the same items, and how it was widened."""

    point: float
    low: float
    high: float
    effective_n: float
    design_effect: float


def clustered_wilson(cells: Sequence[tuple[int, int]], z: float = Z_95) -> ClusteredProportion:
    """A rate over items scored more than once each, with an interval that admits it.

    `cells` is one `(successes, observations)` pair per distinct item. Scoring an item
    twice does not give two independent observations of the system, so treating the rows
    as independent understates the interval, and understates it badly: at ten replicates
    a nominal 95 percent interval over the rows holds about 67 percent of the time, and
    at twenty about 54. The width falls with every replicate added while the rate it is
    meant to cover does not move. tests/test_stats_clustering_coverage.py is the
    simulation that measures it.

    The estimate is the mean of the per-item scores rather than the pooled rate. The two
    differ only where items were scored an unequal number of times, and where they do,
    the pooled rate quietly weights an item by how often it happened to be asked. The
    variance is the variance across those per-item scores over the item count, so the
    item is the sampled unit and the replicate is not.

    That choice of unit is a choice of estimand, and NIST AI 800-3 Appendix A.3,
    doi:10.6028/NIST.AI.800-3, names the two on offer. They share this point estimate and
    differ in variance alone. Benchmark accuracy is the rate on this fixed list of items,
    whose estimator variance `sum_i z_i (1 - z_i) / (n^2 (t - 1))` carries the within-item
    term by itself, since a list that is the whole population contributes no sampling
    variance of its own. Generalized accuracy is the rate on items drawn the way these
    were, whose estimator variance `Var[Z_i] / n` carries the between-item term as well.

    What this function reports is generalized accuracy, because the claim it is computed
    for is a claim about a system rather than about a list: a score card grades a system
    against a threshold, and whoever relies on that grade is meeting items nobody has
    seen. The other estimand stays available to anybody holding a bundle, since
    `stats.replicates.variance_components` splits the same variance into its two additive
    parts and benchmark accuracy is the completion part over the item count.

    The row-counting form the paragraph above measures is neither of them, and A.3.1
    titles it "An Incorrect Standard Error Calculation". It is wrong in both directions at
    once, too wide for benchmark accuracy because it folds in a between-item term that
    estimand does not carry, and too narrow for generalized accuracy wherever an item was
    scored more than once, because it scales that same term by `1 / (n t)` when it belongs
    at `1 / n`.

    That variance is carried into a Wilson interval through an effective sample size
    rather than a normal approximation, because the rates this tool reports sit near zero
    and one often enough that the normal approximation is the thing Wilson was chosen to
    avoid. The effective size is bounded below by the number of items, the case where
    replicates agree perfectly and add nothing, and above by the number of rows, the case
    where they are uncorrelated and the naive figure was right all along. Clamping to
    those two ends is also what keeps a variance of zero, from replicates that happened to
    agree, out of the denominator.
    """
    if not cells:
        return ClusteredProportion(nan, 0.0, 1.0, 0.0, 1.0)
    for successes, observations in cells:
        if observations < 1:
            raise ValueError(f"an item with {observations} observations is not an item")
        if successes < 0 or successes > observations:
            raise ValueError(f"{successes} successes in {observations} observations")

    scores = [successes / observations for successes, observations in cells]
    items = len(cells)
    rows = sum(observations for _, observations in cells)
    point = fmean(scores)

    if items == 1:
        effective = 1.0
    else:
        between = variance(scores)
        spread = point * (1 - point)
        if between <= 0.0 or spread <= 0.0:
            # Every item scored alike, so the between-item variance is unidentifiable
            # here rather than genuinely zero. Fall back to counting items, which is the
            # conservative end of the scale and the honest denominator for 60 items that
            # all passed 10 times out of 10.
            effective = float(items) if spread <= 0.0 else float(rows)
        else:
            effective = spread * items / between

    effective = min(max(effective, float(items)), float(rows))
    low, high = interval(point, effective, z)
    naive = point * (1 - point) / rows if rows else 0.0
    corrected = point * (1 - point) / effective if effective else 0.0
    return ClusteredProportion(
        point=point,
        low=low,
        high=high,
        effective_n=effective,
        design_effect=(corrected / naive) if naive else 1.0,
    )


def format_interval(point: float, low: float, high: float, n: int, dp: int = 1) -> str:
    """Render an already computed rate and interval. The one place the layout is defined.

    Callers holding a computed interval pass it rather than the counts, because an
    interval that has been widened for clustering or for selection cannot be recovered
    from `k` and `n` and printing a recomputed one would quietly contradict the bundle.
    """
    if n == 0:
        return "undefined (n=0)"
    return f"{point * 100:.{dp}f}% (95% CI {low * 100:.{dp}f}-{high * 100:.{dp}f}%, n={n})"


def format_rate(k: int, n: int, dp: int = 1) -> str:
    """Render a proportion the way it has to appear: point, interval, denominator.

    Takes counts, not a rate, so a bare proportion cannot be formatted at all. Valid only
    where the `n` observations are independent, which is what `wilson` assumes.

    >>> format_rate(36, 84)
    '42.9% (95% CI 32.8-53.5%, n=84)'
    >>> format_rate(0, 0)
    'undefined (n=0)'
    """
    if n == 0:
        return "undefined (n=0)"
    point, low, high = wilson(k, n)
    return format_interval(point, low, high, n, dp)
