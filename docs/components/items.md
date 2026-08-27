---
title: Item records
description: >-
  The one-row-per-item observation a pack emits, and why packs are forbidden
  from computing scores.
---

# Item records

One JSON object per evaluated item, written to `/output/items.jsonl`. This is the
load-bearing contract: every number Touchstone reports is computed from these rows, and
they travel in the bundle so anyone can redo the arithmetic.
{ .lede }

```json
{"item_id": "example.001", "stratum": {"language": "pcm"}, "outcome": {"correct": true}}
```

## Who does the maths

Whoever computes the score is who you end up trusting. If a container hands you "94%
accuracy", you are trusting whoever wrote that container, and often that is the people who
would like the number to look good.

So packs here emit one row per item and **no scores at all**. The arithmetic is
Touchstone's, and the rows are in the bundle, so the arithmetic is checkable by whoever was
handed it.

!!! note "The shape of the contract is what enforces this"

    There is no field on an item record for a rate, an interval or a grade. A pack that
    wants to report an average has nowhere to put it. The exception is a [summary-only
    pack](../extending/writing-a-pack.md#summary-only-packs), whose metrics carry no
    interval and are capped when graded, precisely because nobody can check them.

## Fields

| Field | Type | Purpose |
|---|---|---|
| `item_id` | string, required | Stable across runs. The join key for re-analysis. |
| `stratum` | map of string→string | Free-form dimensions, grouped by the estimator. |
| `outcome` | map of string→bool | Booleans, become rates with a denominator. |
| `score` | map of string→float | Continuous measures, become means with intervals. |
| `confidence` | float 0-1, optional | Enables calibration and the confident-and-wrong rate. |
| `cost` | map of string→float | Tokens, latency. |
| `trace_ref` | string, optional | Path inside the bundle to the full prompt and response. |
| `replicate` | integer ≥ 0 | Which repeat this is. Between-replicate variance needs it. |

Unknown fields are refused.

### `item_id`

Stable across runs is the whole requirement. It is what lets a re-analysis join two
evaluations of the same item set, and what lets [replicate](../estimation/replicates.md)
variance count how many *individual items* flipped rather than only how far the aggregate
moved.

### `stratum`

Open dimensions, never an enum. The engine never interprets the values:

```json
{"stratum": {"language": "pcm", "difficulty": "multi_step", "region": "north_east"}}
```

A pack declares the keys and their expected values in its manifest so a plan can be checked
before anything runs, but what they *mean* is the pack's business. This is why a pack for
any market works without a change to the engine. See [Strata and
rollup](../estimation/strata.md).

### `outcome` and `score`

The distinction decides the statistics:

- `outcome` is boolean. It becomes a **rate with a Wilson interval**. See [Rates and
  Wilson](../estimation/rates.md).
- `score` is continuous. It becomes a **mean with a BCa bootstrap interval**. See [Scores
  and the bootstrap](../estimation/scores.md).

An item may carry both, and several of each:

```json
{"item_id": "q.017", "outcome": {"correct": true, "refused": false}, "score": {"latency_ms": 812.0, "rouge_l": 0.61}}
```

### `confidence`

The system's own stated confidence, 0 to 1, for **one** outcome. Which one is declared by
the pack, not chosen at analysis time:

```yaml title="manifest.yaml"
calibrates: "correct"
```

An item carries one confidence, so it is a claim about one outcome, and only the pack knows
which. A pack that declares nothing is never calibrated, because an ECE binned against an
unrelated boolean is a meaningless number that reads as an authoritative one. See
[Calibration](../estimation/calibration.md).

### `trace_ref`

A path inside the bundle to the full prompt and response. This is what turns a disputed row
into something someone can look at.

!!! warning "Traces are not redacted for you"

    If the prompts contain personal data, so does the bundle, and the bundle is the thing
    you hand to someone else. Redact in the pack.

## `pack_id` is written by the harness

Do not emit `pack_id` on a record. The harness stamps it when it merges the per-unit files
and **overwrites anything found there**.

A pack that could name itself could name another one, and every rate computed downstream is
grouped by that field. Two packs both reporting `correct` are not measuring the same thing,
so pooling them into one denominator is exactly the aggregate this tool exists to prevent.

## Emit the observation, not the average

```json title="right"
{"item_id": "q.001", "outcome": {"correct": true}}
{"item_id": "q.002", "outcome": {"correct": false}}
{"item_id": "q.003", "outcome": {"correct": true}}
```

```json title="wrong, and there is nowhere to put it"
{"accuracy": 0.667, "n": 3}
```

The first form can be recomputed, stratified, bootstrapped, compared across replicates and
audited row by row. With the second, you have only the word of whoever wrote the pack.
