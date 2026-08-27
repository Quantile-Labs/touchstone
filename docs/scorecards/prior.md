---
title: Comparing to a prior bundle
description: >-
  Grading movement between two evaluations, and why this is the one reference in
  the tool that reads outside its own bundle.
---

# Comparing to a prior bundle

An indicator can grade **movement**: how a metric changed since the last evaluation.
{ .lede }

```console
$ touchstone grade ./run-005 --score-card card.yaml --prior ./run-004
```

```yaml
- id: accuracy_drift
  name: "Movement in headline accuracy since the last evaluation"
  metric:
    expression: "now - before"
    values:
      now:
        bundle: this
        source: estimate
        name: correct
        pack_id: example_pack
      before:
        bundle: prior
        source: estimate
        name: correct
        pack_id: example_pack
  assessment:
    - level: "A"
      condition: greater_equal
      threshold: -0.01
    - level: "B"
      condition: greater_equal
      threshold: -0.05
    - level: "unfit"
      condition: less_than
      threshold: -0.05
```

`bundle: prior` reaches into the evaluation before this one. A drift indicator is an
[expression](expressions.md) over the same metric in both.

## The one impure reference

Every other command here is a pure function of one bundle, and stays that way.

This is the exception, and it is **explicit in the score card rather than implied by a
flag**, so a reader looking at the card can see which numbers came from where, without
having to know what was on the command line.

The prior bundle is read the same way this one is: offline, from its files, with no Docker.

## Both plan hashes are recorded

```json
{
  "plan_sha256": "a91f4c…",
  "prior_plan_sha256": "81c63db1…"
}
```

Named beside each other for a reason that matters:

!!! warning "Movement between two evaluations run under different plans is movement in the plan as much as in the system"

    If the item count changed, the strata changed, or the pack version changed, the
    difference between the two rates is not a measurement of the system's drift. The two
    hashes are what let a reader check whether they are comparing like with like. If they
    differ, the burden is on whoever quotes the drift to say why the difference does not
    explain it.

## Without `--prior`

Movement indicators come out `ungraded`.

Which is **what a first evaluation of a system honestly is.** There is nothing to compare
against, and reporting no drift would be reporting a measurement that was not made.

## Practical notes

**Keep the plan.** The prior bundle has to be on disk. It is a folder; keep it the way you
would keep any other record.

**The metric has to be in both.** A metric the prior evaluation did not compute makes the
indicator `ungraded`, naming what was missing.

**Direction is yours to get right.** `now - before` is positive when things improved for a
higher-is-better metric, and positive when things got *worse* for an error rate. There is
no `higher_is_better` on an expression, so the thresholds carry the direction. Write the
`description` on each rule.

**The result carries no interval**, like every expression. Two rates over different item
sets have no recorded correlation, and a drift interval computed as though they were
independent would be confidently wrong. See
[Expressions](expressions.md#an-expression-carries-no-interval).
