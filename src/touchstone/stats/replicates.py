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

Both of those describe the run. The third number here describes the estimate: the variance
of a per-item score, split into the part that came from sampling completions and the part
that came from sampling items. Only the first shrinks when a plan buys more replicates.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from statistics import fmean, stdev, variance

from touchstone.contracts import ItemRecord
from touchstone.contracts.estimates import ReplicateVariance, VarianceComponents

COMPONENTS_REFERENCE = (
    "NIST AI 800-3, Appendix A.3, equation 22. doi:10.6028/NIST.AI.800-3. The two "
    "additive sources of variation in a score, from sampling completions per item and "
    "from sampling items."
)


def variance_components(cells: Sequence[tuple[int, int]]) -> VarianceComponents | None:
    """Split the variance of a per-item score into its completion and item parts.

    `cells` is one `(successes, observations)` pair per distinct item, the same shape
    `clustered_wilson` takes. None where the split is not identifiable, which is fewer
    than two items or no item observed more than once.

    NIST AI 800-3 equation 22, with `Pi_i` the success probability of item `i` and `t`
    the trials per item:

        Var[Z_i] = E[Pi_i (1 - Pi_i)] / t   +   Var[Pi_i]
                   completion sampling         item sampling

    A reader asking whether to buy more trials or more items is asking which of those two
    dominates, and one total cannot answer it: the first term falls as `1 / t` and the
    second does not move at all.

    The completion term is the pooled within-item variance divided by the trials per
    item, which is the ANOVA moment estimator, and it carries a `t - 1` rather than a `t`
    for a reason worth writing down. With `z = k / t` and `k` binomial over `t` trials,
    E[z(1 - z)] = Pi(1 - Pi)(t - 1) / t, so the plain mean of `z(1 - z)` understates the
    term by `(t - 1) / t`, which at two replicates is a half and hands the shortfall to
    the item term, where it reads as an item pool more varied than it is. Pooling over
    `sum(t_i - 1)` rather than over `n (t - 1)` is also what lets an item that a replicate
    lost stay in the estimate at the weight it earned.

    The item term is the sample variance across the per-item scores with that sampling
    noise taken back out, floored at zero: a moment estimator of a variance goes negative
    a fair share of the time when the truth is near zero, and a negative variance is not
    a number to put in a bundle. `total` is the sum of what is reported rather than the
    raw sample variance, so where the floor bit the two components still add up.
    """
    for successes, observations in cells:
        if observations < 1:
            raise ValueError(f"an item with {observations} observations is not an item")
        if successes < 0 or successes > observations:
            raise ValueError(f"{successes} successes in {observations} observations")

    within = sum(observations - 1 for _, observations in cells)
    if len(cells) < 2 or within == 0:
        return None

    scores = [successes / observations for successes, observations in cells]
    trials = sum(observations for _, observations in cells) / len(cells)
    pooled = sum(k * (n - k) / n for k, n in cells) / within
    completion = pooled / trials
    item = max(0.0, variance(scores) - completion)

    return VarianceComponents(
        completion=completion,
        item=item,
        total=completion + item,
        trials=trials,
        items=len(cells),
        estimator="anova_moment",
        reference=COMPONENTS_REFERENCE,
    )


def between_replicate(items: Iterable[ItemRecord], metric: str) -> ReplicateVariance:
    """Per-replicate rates for one boolean outcome, their spread, and item-level churn."""
    items = list(items)
    counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    answers: dict[str, set[bool]] = defaultdict(set)
    seen_in: dict[str, set[int]] = defaultdict(set)
    per_item: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for item in items:
        if metric not in item.outcome:
            continue
        counts[item.replicate][0] += int(item.outcome[metric])
        counts[item.replicate][1] += 1
        answers[item.item_id].add(item.outcome[metric])
        seen_in[item.item_id].add(item.replicate)
        per_item[item.item_id][0] += int(item.outcome[metric])
        per_item[item.item_id][1] += 1

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
        # Sorted, so a sum of floats does not depend on the order the rows arrived in.
        components=variance_components([(k, n) for _, (k, n) in sorted(per_item.items())]),
    )
