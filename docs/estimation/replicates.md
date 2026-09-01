---
title: Replicates
description: >-
  Running the whole plan more than once, and the two different numbers that come
  out of it: rate drift and item-level churn.
---

# Replicates

`replicates: 2` runs the whole pack twice. This is what makes run-to-run instability
measurable rather than assumed.
{ .lede }

```yaml title="examples/plan.yaml"
packs:
  - id: "example_pack"
    image: "example_pack:1.0"
    replicates: 2
```

A grade boundary asserted on a single run is a claim about one sample of a stochastic
system, and the honest version of that claim has to say how far the same system moved when
asked again.

## Two numbers, and the second is not derivable from the first

**How far the rate moved** between replicates, and **how many individual items changed
their answer.**

A system can hold a perfectly steady rate while disagreeing with itself on half the items.
That is a different failure from a system whose rate drifts, and only one of the two
numbers can see it:

| | rate spread | unstable items |
|---|---|---|
| Steady and consistent | 0.01 | 3 / 400 |
| **Steady but churning** | **0.01** | **187 / 400** |
| Drifting | 0.09 | 24 / 400 |

Rows one and two look identical on the aggregate. The second system cannot be relied on for
any individual decision, which is what most deployed systems are actually doing.

## What comes out

```json
{
  "metric": "correct",
  "rates": {"0": [188, 200], "1": [191, 200]},
  "mean": 0.9475,
  "sd": 0.0106,
  "spread": 0.015,
  "unstable_items": 11,
  "repeated_items": 200,
  "components": {
    "completion": 0.01375,
    "item": 0.022425,
    "total": 0.036175,
    "trials": 2.0,
    "items": 200,
    "estimator": "anova_moment",
    "reference": "NIST AI 800-3, Appendix A.3, equation 22. ..."
  }
}
```

| Field | Meaning |
|---|---|
| `rates` | `(successes, observations)` per replicate |
| `mean` | mean of the per-replicate rates |
| `sd` | their standard deviation. `null` with fewer than two replicates |
| `spread` | `max - min`. The plainest version of the number |
| `repeated_items` | items seen in more than one replicate |
| `unstable_items` | of those, how many gave more than one distinct answer |
| `components` | the variance of a per-item score, split. `null` below two items or where no item was observed twice |

`unstable_items` is counted by `item_id`, which is why [item ids must be
stable](../components/items.md#item_id) across runs. Without that join key there is no
churn number at all.

## Which of the two more replicates buys

`components` splits the variance of a per-item score into the part that came from sampling
completions and the part that came from sampling items. NIST AI 800-3 equation 22, with
`Pi_i` the success probability of item `i`, `t` the trials per item and `n` the items:

```
Var[Z_i] = E[Pi_i (1 - Pi_i)] / t   +   Var[Pi_i]
           completion sampling         item sampling

Var[S]   = Var[Z_i] / n
```

**Only `completion` falls when a plan buys more replicates, and it falls as `1 / t`.**
`item` is a property of the pool the pack drew its items from and more trials do not move
it at all. Past the point where `completion` is small against `item`, another replicate
buys almost nothing and the same money spent on more items buys the rest of the interval.

Reading the example above. `completion` is 0.01375 at two trials, so four trials would
put it at 0.00688 and the total at 0.02931. An interval scales with the square root of
that, so doubling the bill buys about **10 percent** off the width. `item` is 0.022425 and
four trials leave it at 0.022425, which is where the rest of the width lives. That plan
wants more items.

The split is a moment estimator over the per-item scores. `completion` is the pooled
within-item variance over the trials per item, and `item` is the variance across the
per-item scores with that sampling noise taken back out, floored at zero because a moment
estimator of a variance can go negative when the truth is near it. `trials` is fractional
where a replicate lost an item, because the pooling is over `sum(t_i - 1)` rather than
over a balanced grid.

!!! note "`total` is not the interval"

    `total` is the variance of one item's replicate-averaged score. The variance behind
    the reported rate is `total / items`, and the interval printed beside the rate is a
    Wilson interval at an effective sample size rather than a normal approximation off
    that variance. See [Rates and Wilson](rates.md#the-denominator-is-items-not-rows).

## How it is seeded

`freeze` derives one seed per pack per replicate from the root seed:

```python
seed = sha256(f"{root_seed}:{pack_id}:{replicate}")[:8]
```

They are recorded in `plan.lock.json`, so a rerun matches rather than being asserted to.

!!! warning "Different seeds do not make the system under test vary"

    A replicate varies whatever the pack does with its seed, plus whatever the system does
    on its own. If a pack ignores its seed and the system is deterministic, two replicates
    produce identical rows and `spread` is `0.0`. That is a true statement about that
    setup, and it says nothing about stability under real conditions.

## Grading on it

```yaml title="examples/scorecard.yaml"
- id: run_to_run_stability
  name: "How far the rate moved between replicates"
  metric:
    source: replicate_variance
    name: correct
    pack_id: example_pack
  assessment:
    - level: "A"
      condition: less_equal
      threshold: 0.02
```

A spread is lower-is-better and **has no interval to read**, so `_ci_lower` conditions do
not apply to it. See [Conditions](../scorecards/conditions.md).

## Cost

Replicates multiply everything: run time, API spend, item count. `max_items: 200` at
`replicates: 2` is 400 records and twice the bill.

Two is the useful minimum, the smallest number that produces a spread at all. More
gives a better `sd`, and past three or four you are usually better off spending the same
budget on more items. `components` is how to stop guessing at where that point sits for a
particular plan: run two replicates, read `completion` against `item`, and spend on
whichever one is carrying the variance.
