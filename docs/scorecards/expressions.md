---
title: Expressions
description: >-
  Arithmetic over several metrics, evaluated by walking the tree rather than by
  handing it to eval.
---

# Expressions

An indicator can grade an arithmetic combination of several metrics.
{ .lede }

```yaml
- id: language_gap
  name: "How far the weakest language sits below the headline"
  metric:
    expression: "overall - weakest"
    values:
      overall:
        source: estimate
        name: correct
        pack_id: example_pack
      weakest:
        source: worst_stratum
        name: correct
        pack_id: example_pack
        keys: ["language"]
  assessment:
    - level: "A"
      condition: less_equal
      threshold: 0.05
```

`values` maps each variable in the expression to the metric it stands for. Both are then
read from the bundle and the formula is evaluated.

## There is no `eval` anywhere in the path

This is the security property the module exists for, and it is worth being precise about
what it means.

The obvious implementation, and the one a comparable tool uses, parses the formula, walks
the tree refusing any node not on an allowlist, and then hands the *original string* to
`eval()` with an emptied `__builtins__`. The allowlist is the only thing between a score
card and the interpreter, and the safety argument is a comment listing three reasons the
call is fine.

**This module evaluates the tree itself.** There is no call to defend, and the failure mode
of a missed node type is a raised error rather than an executed one.

Score cards are written by analysts and travel between organisations. The file that decides
a grade is not always written by the person running it. That is the reason to care.

## What is allowed

| | |
|---|---|
| Binary | `+`, `-`, `*`, `/` |
| Comparison | `>`, `>=`, `<`, `<=`, `==` |
| Names | the keys of `values` |
| Numbers | literals |

Anything else, including an attribute access, a call, a subscript or a comprehension,
raises `ScoreCardError`.

## An expression carries no interval

**By design.**

Combining two intervals needs their correlation, and a bundle does not record it. Two rates
computed over the same item set are not independent, because the same items are in both
denominators, so treating them as independent and propagating in quadrature would produce
an interval that is confidently wrong.

The alternative would be to record the joint distribution, which means storing far more than
the bundle format holds and asserting a model of the dependence that nobody checked.

So the expression result is a point, and only the point conditions apply to it:

```yaml
assessment:
  - level: "A"
    condition: less_equal      # not less_equal_ci_upper
    threshold: 0.05
```

Asking for an interval condition on an expression raises.

!!! warning "This means an expression indicator has the failure mode the rest of the tool avoids"

    A gap of 0.04 between two rates each measured on 60 items is not meaningfully different
    from a gap of 0.09. The point conditions will grade it anyway. Use expressions where
    the inputs are large, and read the `measured` list in the output. Every number that
    went in is recorded there.

## The output records the working

```json
{
  "id": "language_gap",
  "verdict": "graded",
  "level": "A",
  "expression": "overall - weakest",
  "value": 0.043,
  "measured": [
    {"ref": {"name": "correct", "source": "estimate"}, "value": 0.94, "low": 0.92, "high": 0.95, "n": 1000},
    {"ref": {"name": "correct", "source": "worst_stratum"}, "value": 0.897, "low": 0.85, "high": 0.93, "n": 210, "stratum": {"language": "ha"}}
  ]
}
```

`value` is the computed result, the number the ladder was actually walked against, and the
only place it appears.

That separation is deliberate: a report that grades a difference between two rates and
prints one of the rates beside the grade is showing a number that did not decide anything.

`measured` holds every input, each with its own interval and denominator, so a reader can see
what the point was built from.
