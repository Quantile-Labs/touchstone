---
title: Calibration
description: >-
  Expected calibration error against the system's own stated confidence, and the
  confident-and-wrong rate a regulator reads first.
---

# Calibration

Does a stated confidence mean what it says?
{ .lede }

A system that is right 60% of the time and says `0.95` every time is not merely inaccurate
is **unusable**, because nothing downstream can tell its good answers from its bad
ones. That is a different defect from a low accuracy rate and it needs its own number.

## What the pack has to provide

Two things on the item record:

```json
{"item_id": "q.017", "outcome": {"correct": false}, "confidence": 0.93}
```

And one declaration in the manifest:

```yaml title="manifest.yaml"
calibrates: "correct"
```

An item carries **one** confidence, so it is a claim about **one** outcome, and only the
pack knows which.

!!! danger "A pack that declares nothing is never calibrated"

    This is deliberate. An ECE binned against an unrelated boolean is a meaningless number
    that reads as an authoritative one, in a sealed evidence bundle, to someone deciding
    whether to deploy the system.

`freeze` reads `calibrates` out of the image and pins it into `plan.lock.json`, so what was
calibrated is part of the frozen plan rather than a flag somebody typed after seeing the
result.

## Expected calibration error

Confidences are put into ten equal-width bins over `[0, 1]`. In each bin, the mean stated
confidence is compared with the observed accuracy. ECE is the **sample-weighted mean
absolute gap** across bins.

```json
{
  "metric": "correct",
  "n": 400,
  "ece": 0.147,
  "unscored": 0,
  "bins": [
    {"low": 0.5, "high": 0.6, "n": 12, "mean_confidence": 0.556, "accuracy": 0.583},
    {"low": 0.9, "high": 1.0, "n": 241, "mean_confidence": 0.961, "accuracy": 0.797}
  ],
  "parameters": {"bins": 10},
  "reference": "Naeini, M. P., Cooper, G. F., Hauskrecht, M. (2015). …"
}
```

The `bins` list is the reliability curve. An empty bin contributes nothing, as in the cited
papers. `unscored` counts items that reported the outcome but carried no confidence.

Bins are right-closed, so a confidence of exactly `1.0` lands in the top bin rather than
falling off the end.

> Naeini, M. P., Cooper, G. F., Hauskrecht, M. (2015). Obtaining well calibrated
> probabilities using Bayesian binning. *AAAI 2015*, 2901-2907.
>
> Guo, C., Pleiss, G., Sun, Y., Weinberger, K. Q. (2017). On calibration of modern neural
> networks. *ICML 2017*, 1321-1330.

Ten bins is the convention the cited papers report.

## Confident and wrong

```python
confident_and_wrong(items, "correct", threshold=0.9)  # -> (wrong, scored)
```

The count of items where the system stated `≥ 0.9` confidence **and was wrong**, over the
count of items that carried a confidence at all.

This is the indicator a regulator reads first. A wrong answer delivered hesitantly can be
caught downstream; **one delivered at 0.95 cannot.**

It is returned as counts rather than a rate, so the caller has to attach an interval. Same
house rule as everywhere else. See [Rates and Wilson](rates.md#no-bare-proportion-leaves-the-laboratory).

## Overriding at analysis time

```console
$ touchstone estimate ./run-004 --calibrate correct --calibrate refused
```

`--calibrate` overrides the pack's declaration, for re-analysis. Repeat for more than one.

Without it the frozen plan decides. Use the override when you are re-examining a bundle and
want to see the curve against a different outcome. Be aware that you have stepped outside
what the pack said its confidence meant.

## Grading on it

```yaml title="examples/scorecard.yaml"
- id: calibration
  name: "Expected calibration error of the system's own confidence"
  metric:
    source: calibration
    name: correct
    pack_id: example_pack
  assessment:
    - level: "A"
      condition: less_equal
      threshold: 0.05
```

ECE is lower-is-better and carries no interval, so `_ci_lower` and `_ci_upper` conditions
do not apply to it. See [Conditions](../scorecards/conditions.md).
