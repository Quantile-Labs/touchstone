# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Calibration: does a stated confidence mean what it says?

A system that is right 60 percent of the time and says 0.95 every time is not merely
inaccurate, it is unusable, because nothing downstream can tell its good answers from its
bad ones. That is a different defect from a low accuracy rate and it needs its own number.

Binning is the standard equal-width scheme.

  Naeini, M. P., Cooper, G. F., Hauskrecht, M. (2015). Obtaining well calibrated
  probabilities using Bayesian binning. AAAI 2015, 2901-2907.
  Guo, C., Pleiss, G., Sun, Y., Weinberger, K. Q. (2017). On calibration of modern neural
  networks. ICML 2017, 1321-1330.
"""

from collections.abc import Iterable

from touchstone.contracts import ItemRecord
from touchstone.contracts.estimates import Calibration, CalibrationBin

ECE_REFERENCE = (
    "Naeini, M. P., Cooper, G. F., Hauskrecht, M. (2015). Obtaining well calibrated "
    "probabilities using Bayesian binning. AAAI 2015, 2901-2907. Equal-width binning as "
    "used by Guo et al. (2017), ICML, 1321-1330."
)

BINS = 10
"""Equal-width bins over [0, 1]. Ten is the convention the cited papers report."""


def _bin_index(confidence: float, bins: int) -> int:
    """Right-closed bins, so a confidence of exactly 1.0 lands in the top bin."""
    index = int(confidence * bins)
    return min(index, bins - 1)


def calibration(items: Iterable[ItemRecord], metric: str, bins: int = BINS) -> Calibration:
    """Reliability curve and expected calibration error for one boolean outcome.

    ECE is the sample-weighted mean absolute gap between stated confidence and observed
    accuracy across bins. An empty bin contributes nothing, as in the cited papers.
    """
    if bins < 1:
        raise ValueError(f"bins has to be at least 1, got {bins}")

    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    unscored = 0
    for item in items:
        if metric not in item.outcome:
            continue
        if item.confidence is None:
            unscored += 1
            continue
        buckets[_bin_index(item.confidence, bins)].append((item.confidence, item.outcome[metric]))

    total = sum(len(bucket) for bucket in buckets)
    curve = []
    error = 0.0
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        mean_confidence = sum(confidence for confidence, _ in bucket) / len(bucket)
        accuracy = sum(int(correct) for _, correct in bucket) / len(bucket)
        curve.append(
            CalibrationBin(
                low=index / bins,
                high=(index + 1) / bins,
                n=len(bucket),
                mean_confidence=mean_confidence,
                accuracy=accuracy,
            )
        )
        error += (len(bucket) / total) * abs(mean_confidence - accuracy)

    return Calibration(
        metric=metric,
        n=total,
        ece=error if total else None,
        bins=curve,
        unscored=unscored,
        parameters={"bins": bins},
        reference=ECE_REFERENCE,
    )


def confident_and_wrong(
    items: Iterable[ItemRecord], metric: str, threshold: float = 0.9
) -> tuple[int, int]:
    """Counts of (stated confidence at or above `threshold` and wrong, all items scored).

    Returned as counts rather than a rate so the caller has to attach an interval. This
    is the indicator a regulator reads first: a wrong answer delivered hesitantly can be
    caught downstream, one delivered at 0.95 cannot.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold has to be in [0, 1], got {threshold}")

    wrong = 0
    scored = 0
    for item in items:
        if metric not in item.outcome or item.confidence is None:
            continue
        scored += 1
        if item.confidence >= threshold and not item.outcome[metric]:
            wrong += 1
    return wrong, scored


def confident_and_wrong_by_item(
    items: Iterable[ItemRecord], metric: str, threshold: float = 0.9
) -> list[tuple[int, int]]:
    """The same counts split by item, one `(wrong, scored)` pair per distinct item.

    What the interval has to be computed over. A system asked the same question three
    times and confidently wrong all three has failed once, not three times, so pooling the
    rows would report the rate over a denominator that never existed. See
    `stats.proportion.clustered_wilson`.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold has to be in [0, 1], got {threshold}")

    per_item: dict[str, list[int]] = {}
    for item in items:
        if metric not in item.outcome or item.confidence is None:
            continue
        pair = per_item.setdefault(item.item_id, [0, 0])
        pair[1] += 1
        if item.confidence >= threshold and not item.outcome[metric]:
            pair[0] += 1
    return [(wrong, scored) for _, (wrong, scored) in sorted(per_item.items())]
