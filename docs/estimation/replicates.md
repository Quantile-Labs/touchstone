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
  "repeated_items": 200
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

`unstable_items` is counted by `item_id`, which is why [item ids must be
stable](../components/items.md#item_id) across runs. Without that join key there is no
churn number at all.

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
budget on more items.
