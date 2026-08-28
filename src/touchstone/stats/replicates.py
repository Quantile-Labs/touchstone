# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Between-replicate variance: how much of a result is the system and how much is the run.

01-ASQI-TEARDOWN.md section 3.2. A grade boundary asserted on a single run is a claim
about one sample of a stochastic system, and the honest version of that claim has to say
how far the same system moved when asked again. Two numbers do that: how far the rate
moved between replicates, and how many individual items changed their answer.

The second is not derivable from the first. A system can hold a steady rate while
disagreeing with itself on half the items, and that is a different failure from a system
whose rate drifts.
"""

from collections import defaultdict
from collections.abc import Iterable
from statistics import fmean, stdev

from touchstone.contracts import ItemRecord
from touchstone.contracts.estimates import ReplicateVariance


def between_replicate(items: Iterable[ItemRecord], metric: str) -> ReplicateVariance:
    """Per-replicate rates for one boolean outcome, their spread, and item-level churn."""
    items = list(items)
    counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    answers: dict[str, set[bool]] = defaultdict(set)
    seen_in: dict[str, set[int]] = defaultdict(set)

    for item in items:
        if metric not in item.outcome:
            continue
        counts[item.replicate][0] += int(item.outcome[metric])
        counts[item.replicate][1] += 1
        answers[item.item_id].add(item.outcome[metric])
        seen_in[item.item_id].add(item.replicate)

    rates = {replicate: (pair[0], pair[1]) for replicate, pair in sorted(counts.items())}
    proportions = [k / n for k, n in rates.values() if n]

    repeated = [item_id for item_id, where in seen_in.items() if len(where) > 1]
    unstable = sum(1 for item_id in repeated if len(answers[item_id]) > 1)

    return ReplicateVariance(
        metric=metric,
        rates=rates,
        mean=fmean(proportions) if proportions else None,
        sd=stdev(proportions) if len(proportions) > 1 else None,
        spread=max(proportions) - min(proportions) if proportions else None,
        unstable_items=unstable,
        repeated_items=len(repeated),
    )
