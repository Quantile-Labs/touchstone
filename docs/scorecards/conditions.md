---
title: Conditions
description: >-
  The eight rules a score card can apply, and why the three interval conditions
  are the ones that matter.
---

# Conditions

Eight conditions. Five compare the point estimate; three read the interval.
{ .lede }

| Condition | Reads | Awards when |
|---|---|---|
| `greater_equal` | point | `value >= threshold` |
| `greater_than` | point | `value > threshold` |
| `less_equal` | point | `value <= threshold` |
| `less_than` | point | `value < threshold` |
| `equal_to` | point | `value == threshold` |
| **`greater_equal_ci_lower`** | **interval** | the **whole interval** clears the threshold |
| **`less_equal_ci_upper`** | **interval** | the **whole interval** sits under the threshold |
| **`threshold_crossed_by_interval`** | **interval** | the threshold lies **inside** the interval |

Every condition compares against a number, so `threshold` is always required.

## The interval conditions

These are the reason the tool exists.

### `greater_equal_ci_lower`

Reads the **bottom** of the interval, so a wide interval cannot buy a level the sample does
not support.

```yaml
- level: "A"
  condition: greater_equal_ci_lower
  threshold: 0.9
```

Three outcomes, not two:

```text
threshold = 0.9

  low ────────── high
       0.91  0.95            low >= 0.9      -> awarded
  0.88 ──────── 0.93         straddles 0.9   -> INDETERMINATE
  0.71 ── 0.84               high < 0.9      -> refused
```

It awards only when the whole interval clears the threshold, refuses only when the whole
interval sits below it, and **reports the overlap as what it is rather than resolving it in
either direction.**

Compare with `greater_equal`, which reads the point estimate: a run of 50 items at 94%
(95% CI 83.5-98.8%) would be awarded `A` by `greater_equal` and reported `indeterminate` by
`greater_equal_ci_lower`. Fifty items cannot separate 94% from a 90% bar, and
`greater_equal_ci_lower` is the condition that says so.

### `less_equal_ci_upper`

The mirror, for lower-is-better metrics that carry an interval: an error rate, a
confident-and-wrong rate.

```yaml
- level: "A"
  condition: less_equal_ci_upper
  threshold: 0.02
```

Awards only when the **top** of the interval is under the threshold.

### `threshold_crossed_by_interval`

Awards when the threshold lies inside the interval, `low <= threshold <= high`.

This one has no indeterminate outcome; it is a direct test of whether the evidence is
consistent with a particular value. Use it to say "the evidence does not rule out the
target", which is a different claim from "the evidence supports the target".

## An interval condition on a metric with no interval is an error

```text
ScoreCardError: greater_equal_ci_lower needs an interval and this metric has none
```

The condition raises, and grading stops there.

`calibration` and `replicate_variance` are single numbers. Neither has a sampling
distribution this codebase is willing to assert, so a card that asks for the lower bound of
an ECE is a card with a mistake in it, and saying so is more useful than picking a
convention.

Grade those with the point conditions:

```yaml
- id: calibration
  metric: {source: calibration, name: correct, pack_id: example_pack}
  assessment:
    - level: "A"
      condition: less_equal
      threshold: 0.05
```

## The ladder is walked in order

`assessment` is ordered **best level first**, and the first rule that holds decides.

```yaml
assessment:
  - level: "A"
    condition: greater_equal_ci_lower
    threshold: 0.9
  - level: "B"
    condition: greater_equal_ci_lower
    threshold: 0.7
  - level: "C"
    condition: greater_equal_ci_lower
    threshold: 0.5
  - level: "unfit"
    condition: greater_equal
    threshold: 0.0
```

The last rung is `greater_equal: 0.0` on purpose. It always holds for a rate, which makes
`unfit` the floor rather than leaving a value that clears nothing as `ungraded`. A card
without a floor will produce `ungraded` for a genuinely bad system, and `ungraded` reads as
"not measured" rather than "measured and bad".

If a rule straddles, the descent stops there and the levels below become the floor. See
[Indeterminate](indeterminate.md).

## `description`

```yaml
- level: "A"
  condition: greater_equal_ci_lower
  threshold: 0.9
  description: "the lower bound clears 0.9"
```

Optional, and carried into `scorecard.json` on the rule that decided. It is what a reader
sees next to the grade, so write it for them rather than for you.
