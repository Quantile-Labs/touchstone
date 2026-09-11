# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Movement between two evaluations, with an interval over the change itself.

Two runs over the same items are not independent samples. A system that finds an item hard
finds it hard both times, so the two rates move together, and an interval for their
difference built as though they did not is wider than the evidence. Pairing the items takes
that shared difficulty out, which is why a paired comparison is the one NIST AI 800-2 ipd
Practice 3.1 asks for when two models were scored on the same set.
"""

from collections.abc import Sequence
from math import sqrt
from statistics import fmean, variance
from typing import NamedTuple

from touchstone.stats.proportion import Z_95

PAIRED_REFERENCE = (
    "Miller, E. (2024). Adding Error Bars to Evals: A Statistical Approach to Language "
    "Model Evaluations. arXiv:2411.00640, section 4.2, equation 7, with the normal "
    "interval of equation 3."
)

WILSON_DIFFERENCE_REFERENCE = (
    "Newcombe, R. G. (1998). Interval estimation for the difference between independent "
    "proportions: comparison of eleven methods. Statistics in Medicine 17(8), 873-890. "
    "The method combining the Wilson score intervals for the two proportions."
)

LIMITS_DIFFERENCE_REFERENCE = (
    "Zou, G. Y., Donner, A. (2008). Construction of confidence limits about effect "
    "measures: a general approach. Statistics in Medicine 27(10), 1693-1702."
)

Bounds = tuple[float, float, float]
"""A point and the interval around it, `(point, low, high)`."""


class PairedDifference(NamedTuple):
    """A mean per-item difference, its interval, and what the interval was computed from."""

    point: float
    low: float
    high: float
    standard_error: float
    items: int


def paired_difference(
    pairs: Sequence[tuple[float, float]], z: float = Z_95, bounded: bool = False
) -> PairedDifference:
    """The mean of the per-item differences and a normal interval on their standard error.

    `pairs` is one `(now, before)` per item, each already averaged over that item's
    replicates. That is where Miller folds resampling in, before the difference is taken,
    so an item scored ten times contributes one difference and not ten.

    Miller equation 7, with `d_i` the difference on item `i` over `n` items:

        SE = sqrt( Var(d) / n ),   Var the sample variance, over n - 1

    `bounded` clamps the interval to [-1, 1], the range a difference of two rates can take,
    because a normal interval near either end does not know that range exists.
    """
    if len(pairs) < 2:
        raise ValueError(f"a paired standard error needs at least two items, got {len(pairs)}")
    differences = [now - before for now, before in pairs]
    point = fmean(differences)
    error = sqrt(variance(differences) / len(differences))
    low, high = point - z * error, point + z * error
    if bounded:
        low, high = max(-1.0, low), min(1.0, high)
    return PairedDifference(point, low, high, error, len(pairs))


def unpaired_difference(now: Bounds, before: Bounds) -> Bounds:
    """`now` minus `before`, from each figure's own interval, as though the two were independent.

    Each side's distance from its point to a limit stands in for its own uncertainty in that
    direction, and the two are added in quadrature: the lower limit of the difference takes
    the lower side of `now` and the upper side of `before`, and the upper limit the reverse.
    Over two Wilson intervals this is the method Newcombe recommends, and it keeps the
    asymmetry each interval has near zero and one where a pooled standard error would throw
    it away. Over any other pair of intervals, a BCa mean included, it is Zou and Donner's
    general construction.

    Independence is the assumption. Where the two runs shared items and agreed about which
    were hard, it overstates the width, which is the safe side to be wrong on, and it is
    what runs when pairing cannot be shown to be valid.
    """
    point_now, low_now, high_now = now
    point_before, low_before, high_before = before
    point = point_now - point_before
    below = sqrt((point_now - low_now) ** 2 + (high_before - point_before) ** 2)
    above = sqrt((high_now - point_now) ** 2 + (point_before - low_before) ** 2)
    return point, point - below, point + above
