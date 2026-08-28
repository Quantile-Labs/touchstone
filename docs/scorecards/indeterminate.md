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
headline_accuracy: indeterminate, A or C  [0.91, 0.8783 to 0.9345, n=400]
    the interval spans the A boundary of 0.9, so the grade is A or C and the evidence does not say which
```

## What happened there

The ladder is walked best-first. At the `A` rung, `greater_equal_ci_lower: 0.9`:

```text
threshold 0.9
        0.8783 ──────●────── 0.9345
                  0.91
                    ↑
                   0.9 is inside the interval
```

The interval straddles. The descent stops, and the levels below the straddled rung become
the floor.

The result is that the grade is `A` **or** the best level that still holds below, `C` in
this case, because `B`'s threshold of 0.7 is cleared outright by the lower bound. The
honest statement is that it is one of these and the evidence does not say which.

## Why this is not rounding down

Awarding `C` would be a claim: that the system does not clear 0.9. The evidence does not
support that claim either. A point estimate of 0.91 with a lower bound of 0.878 is entirely
consistent with a true rate above 0.9.

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
  "between": ["A", "C"],
  "rule": {"level": "A", "condition": "greater_equal_ci_lower", "threshold": 0.9},
  "reason": "the interval spans the A boundary of 0.9, so the grade is A or C",
  "value": 0.91,
  "measured": [{"value": 0.91, "low": 0.8783, "high": 0.9345, "n": 400}]
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
the interval spans the unfit boundary of 0.3, and no lower rule holds,
so the grade is unfit or no grade at all
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
  "reason": "access_tier caps this at C, which is at or below both ends of A to C, so the interval no longer decides the grade"
}
```

`uncapped_level` keeps the better end of the original range, so the working is still
visible.

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
