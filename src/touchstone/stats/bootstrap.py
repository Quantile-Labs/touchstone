# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""BCa bootstrap intervals for continuous measures.

A rubric score has no closed-form interval, and the percentile bootstrap is biased
whenever the statistic is skewed, which a bounded rubric always is. BCa corrects for both
the bias and the skew.

  Efron, B. (1987). Better bootstrap confidence intervals. Journal of the American
  Statistical Association 82(397), 171-185.
  Efron, B., Tibshirani, R. J. (1993). An Introduction to the Bootstrap, chapter 14.
  Chapman and Hall.

Stdlib only, and seeded, so an interval in a bundle is reproducible byte for byte by
anyone holding the bundle.

Resampling draws through `random()` rather than `randrange()` on purpose. The Python
documentation guarantees the seeded sequence of `random()` and undertakes to keep it
across versions; `randrange()` reaches it through `_randbelow`, which is an implementation
detail and has changed before. An interval that quietly moved on a Python upgrade would
be the worst kind of defect here, because the number it moved is already sealed in
somebody's bundle. tests/test_stats_bootstrap.py pins the arithmetic to fixed values so
a change fails the build rather than the client.
"""

from collections.abc import Callable, Sequence
from math import floor, isfinite
from random import Random
from statistics import NormalDist, fmean

BCA_REFERENCE = (
    "Efron, B. (1987). Better bootstrap confidence intervals. Journal of the American "
    "Statistical Association 82(397), 171-185."
)

RESAMPLES = 2000
"""Efron and Tibshirani, chapter 14: intervals want at least 1000, and 2000 is the usual
working figure. Higher costs only time, and the whole computation is offline."""

_NORMAL = NormalDist()


def _percentile(ordered: Sequence[float], alpha: float) -> float:
    """The B*alpha-th ordered value, the convention in Efron and Tibshirani chapter 13."""
    index = int(floor(alpha * len(ordered)))
    return ordered[min(max(index, 0), len(ordered) - 1)]


def _acceleration(sample: Sequence[float], statistic: Callable[[Sequence[float]], float]) -> float:
    """Jackknife acceleration. Zero when the leave-one-out values do not vary, which is
    the degenerate case rather than a skew of zero."""
    jackknife = [statistic([*sample[:index], *sample[index + 1 :]]) for index in range(len(sample))]
    centre = fmean(jackknife)
    deviations = [centre - value for value in jackknife]
    numerator = sum(deviation**3 for deviation in deviations)
    denominator = 6 * (sum(deviation**2 for deviation in deviations) ** 1.5)
    return numerator / denominator if denominator else 0.0


def bootstrap_bca(
    sample: Sequence[float],
    statistic: Callable[[Sequence[float]], float] = fmean,
    confidence: float = 0.95,
    resamples: int = RESAMPLES,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Bias-corrected and accelerated interval. Returns (point, low, high).

    `seed` is required in practice rather than optional: an interval nobody else can
    recompute is not evidence. The caller passes the seed the run was frozen with, so the
    number in the bundle falls out of the plan.
    """
    sample = list(sample)
    if not sample:
        raise ValueError("cannot bootstrap an empty sample")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence has to be in (0, 1), got {confidence}")
    if resamples < 1:
        raise ValueError(f"resamples has to be at least 1, got {resamples}")

    point = statistic(sample)
    if len(sample) == 1:
        return point, point, point

    rng = Random(seed)
    size = len(sample)
    # int(random() * size) is uniform to within the granularity of a 53 bit float, which
    # is nowhere near the precision any bootstrap interval is quoted to.
    replicates = sorted(
        statistic([sample[int(rng.random() * size)] for _ in range(size)]) for _ in range(resamples)
    )

    below = sum(1 for value in replicates if value < point)
    if below in (0, resamples):
        # Every resample landed on one side of the estimate, so the bias correction is
        # undefined. A constant sample is the usual cause and its interval is a point.
        return point, replicates[0], replicates[-1]

    bias = _NORMAL.inv_cdf(below / resamples)
    accel = _acceleration(sample, statistic)

    tail = (1.0 - confidence) / 2.0
    bounds = []
    for probability in (tail, 1.0 - tail):
        z = _NORMAL.inv_cdf(probability)
        adjusted = bias + (bias + z) / (1 - accel * (bias + z))
        if not isfinite(adjusted):
            bounds.append(_percentile(replicates, probability))
            continue
        bounds.append(_percentile(replicates, _NORMAL.cdf(adjusted)))

    low, high = sorted(bounds)
    return point, low, high
