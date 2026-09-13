---
title: Indeterminate
description: >-
  When the interval straddles a threshold, the grade is neither letter. Why that
  is a finding rather than a missing value.
---

# Indeterminate

If the error bar crosses the threshold, the honest answer is `indeterminate`. The report
says so, and names the two levels the evidence sits between.
{ .lede }

```console
Correct answers over the whole sample (headline_accuracy)
  Grade: B or C, inconclusive
  Score: 0.72, likely range 0.6741 to 0.7617, 400 results
  Reason: The likely range crosses the B threshold (0.7), so the grade is B or C
```

## What happened there

The ladder in `examples/scorecard.yaml` is walked best-first. `A` needs a lower bound of
0.9, and the whole interval sits below it, so `A` is refused. At the `B` rung,
`greater_equal_ci_lower: 0.7`:

```text
threshold 0.7
        0.6741 ──────●────── 0.7617
                  0.72
                    ↑
                   0.7 is inside the interval
```

The interval straddles. The descent stops, and the levels below the straddled rung become
the floor.

The grade is `B` **or** the best level that holds below it. `C` needs a lower bound of 0.5,
which 0.6741 clears, so the grade is `B` or `C`, and the evidence does not say which.

## Why this is not rounding down

Awarding `C` would be a claim: that the system does not clear 0.7. The evidence does not
support that claim either. A point estimate of 0.72 with a lower bound of 0.674 is entirely
consistent with a true rate above 0.7.

The sample backs neither letter. `indeterminate` says exactly that, and it carries the
number that produced it so a reader can decide what to do about it.

**The usual thing to do about it is collect more items.** That is the useful signal:
`indeterminate` on an indicator you care about tells you the evaluation is too small to
decide, before someone builds a decision on it.

## In `scorecard.json`

```json
{
  "id": "headline_accuracy",
  "verdict": "indeterminate",
  "level": null,
  "between": ["B", "C"],
  "rule": {"level": "B", "condition": "greater_equal_ci_lower", "threshold": 0.7},
  "reason": "the likely range crosses the B threshold (0.7), so the grade is B or C",
  "value": 0.72,
  "measured": [{"value": 0.72, "low": 0.6741, "high": 0.7617, "n": 400}]
}
```

| Field | Meaning |
|---|---|
| `level` | `null`. No level was awarded. |
| `between` | the level refused and the next one down, **in that order** |
| `rule` | the rule whose boundary the interval straddles |
| `reason` | why, in one line, printed in the report |

## When no lower rule holds

If the straddled rung is the last one that could have held, `between` carries a single
level:

```text
the likely range crosses the unfit threshold (0.3) and no lower rule applies,
so the grade is unfit or none
```

## A ceiling can settle it

If the [access tier ceiling](ceilings.md) sits at or below **both** ends of the
indeterminate range, the range collapses and the verdict becomes `graded`.

The reasoning: if the grade could not have exceeded the ceiling either way, then the
interval was never deciding anything that mattered.

```json
{
  "verdict": "graded",
  "level": "C",
  "uncapped_level": "A",
  "ceiling": "C",
  "ceiling_reason": "access_tier",
  "between": [],
  "reason": "the likely range allows A or C, and black box access is capped at C"
}
```

`uncapped_level` keeps the better end of the original range, so the working is still
visible.

## A ceiling inside the range

A ceiling between the two ends lowers the better end, and the verdict stays
`indeterminate`. The reason carries both steps, so it names the same levels as the grade.
On a card with rungs at `A` (0.9) and `C` (0.7), a range of `A` or `C` under a `B`
ceiling:

```json
{
  "verdict": "indeterminate",
  "between": ["B", "C"],
  "ceiling": "B",
  "ceiling_reason": "access_tier",
  "reason": "the likely range crosses the A threshold (0.9), so the grade is A or C; black box access is capped at B, so the grade is B or C"
}
```

A ceiling at or above the better end leaves the range as it was, and `ceiling` stays
`null`. The example at the top of this page is graded under a `B` ceiling for that reason.

## `indeterminate` is not `ungraded`

Three different things:

| Verdict | Means |
|---|---|
| `graded` | a level was awarded |
| `indeterminate` | **measured, and the evidence does not separate two levels** |
| `ungraded` | no rule held at all, or the number was not in the bundle |

`ungraded` reads as "not assessed". `indeterminate` reads as "assessed, and the assessment
does not resolve". Collapsing them would hide the second inside the first, and the second is
the one that tells you to collect more data.
