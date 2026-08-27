---
title: Tier ceilings
description: >-
  The best level an evaluation at a given access tier may reach, and the
  per-indicator override that makes the ceiling a property of the pair.
---

# Tier ceilings

A claim cannot exceed the evidence the access allowed.
{ .lede }

```yaml title="examples/scorecard.yaml"
tier_ceilings:
  black_box: "B"
  grey_box: "A"

summary_only_ceiling: "C"
```

The plan declares `access_tier`. The card declares what each tier may reach. `grade`
applies the cap to computed and human-assessed indicators alike.

## Why

An evaluation that could only see inputs and outputs cannot support a claim that needed
weights, training data or internal logs, however good the numbers came out.

The alternative is a report that says "A" on evidence that could never have distinguished
`A` from `B`, and a reader with no way to know. The ceiling makes that visible rather than
requiring the reader to reconstruct it from the methodology section.

## The vocabulary is the card's

The engine does not know what tiers exist. `black_box` and `grey_box` appear in the example
because that card declares them.

**A tier absent from the map is uncapped**, and that has to be written down. An access tier in a plan that the card does not recognise is a hard error in
`grade`, not a silent pass. A new tier is a YAML change.

## What a cap looks like in the output

```json
{
  "id": "headline_accuracy",
  "verdict": "graded",
  "level": "B",
  "uncapped_level": "A",
  "ceiling": "B",
  "ceiling_reason": "access_tier",
  "value": 0.94
}
```

`uncapped_level` is what the ladder awarded before the ceiling applied. It is kept so a
reader can see **the claim the evidence supported and the reason it was not made**. Both
together tell an operator what deeper access would buy them.

`ceiling` and `ceiling_reason` are set only where a ceiling actually bit. An indicator that
came out at `C` under a `B` ceiling has neither.

## `summary_only_ceiling`

```yaml
summary_only_ceiling: "C"
```

The best level a metric from a pack that emitted no item records may reach.

A [summary-only pack](../extending/writing-a-pack.md#summary-only-packs) asserts its
numbers, and nobody can recompute them from the bundle. The whole argument of this tool is
that a number you can check is worth more than a number you cannot, and this ceiling is
where that argument becomes arithmetic.

`ceiling_reason` is `summary_only` when this is what bit.

Leaving it `null` leaves such metrics uncapped, which is advised against.

## Per-indicator ceilings

The ceiling is a property of **the pair**, the tier and the indicator together:

```yaml
indicators:
  - id: calibration
    metric: {source: calibration, name: correct, pack_id: example_pack}
    tier_ceilings:
      black_box: null
      grey_box: "A"
    assessment: [...]
```

A black-box evaluation can measure headline accuracy **completely** and cannot measure some
other property **at all**. One ceiling for a whole card either caps the first for no
reason, or lets the second be claimed on evidence that does not exist.

An indicator's own `tier_ceilings` replaces the card's map for that indicator.

### `null` means not assessable

A tier mapped to `null` is one where this indicator cannot be assessed at all. It returns
`ungraded` naming the tier, and, importantly, **the metric it would have read is never
looked for**, so a bundle that legitimately does not hold it is not an error.

That is what lets one card cover several access tiers without a black-box run failing
because it has no entry for a metric it could never have produced.

## Ceilings and `indeterminate`

If the ceiling sits at or below both ends of an indeterminate range, the range collapses and
the verdict becomes `graded`. See [Indeterminate](indeterminate.md#a-ceiling-can-settle-it).
