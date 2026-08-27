---
title: Re-analysis
description: >-
  Recomputing estimates and grades from a bundle you were handed, without
  rerunning anything.
---

# Re-analysis

`items.jsonl` is the observation. Everything else is derived from it, and can be derived
again by anyone holding the bundle.
{ .lede }

This is the property that makes the format worth the overhead. A reader who disagrees with
how a number was computed does not have to take it up with whoever computed it; they can
redo it.

## Recompute the estimates

```console
$ touchstone estimate ./run-004 --by language --by difficulty
```

Runs against the bundle you were handed. No Docker, no network, nothing rerun. It reads
`items.jsonl` and rewrites `estimates.json`.

Split it differently, cross different keys, look at a stratum the original analysis did not
report:

```console
$ touchstone estimate ./run-004 --by region
```

If the pack tagged its items with `region`, the cells are there whether or not the first
analysis looked at them.

!!! warning "Re-estimating overwrites `estimates.json` and invalidates the manifest"

    Work on a copy of the bundle, or re-seal with `touchstone bundle` afterwards and be
    clear that the result is your analysis rather than the one you were handed. `verify`
    against the original hashes is how anyone tells the two apart.

## Grade against your own card

```console
$ touchstone grade ./run-004 --score-card my-card.yaml
```

The most useful thing in the format. The bundle carries the numbers; the thresholds are
yours.

A procurement team with a different risk appetite from the vendor's does not have to argue
about the vendor's rubric. They apply their own to the same rows, and the disagreement
becomes a disagreement about policy, which is where it belongs.

The access tier ceiling still applies, and still comes from the frozen plan rather than from
your card's assumptions about it. You cannot grade a black-box run as though it were
white-box by writing a more generous card.

## Re-bin the calibration

```console
$ touchstone estimate ./run-004 --calibrate refused
```

Overrides the outcome the pack declared its confidence was a claim about. Useful when you
are re-examining a bundle and want the reliability curve against something else. Be aware
that you have stepped outside what the pack said its confidence meant. See
[Calibration](../estimation/calibration.md#overriding-at-analysis-time).

## Do the arithmetic somewhere else

`estimates.json` carries the estimator, its parameters and a citation beside every number,
so the sums can be redone in R, in a spreadsheet, or on paper.

```console
$ jq -r '.[] | select(.metric=="correct") | [.stratum.language, .k, .n] | @tsv' \
    run-004/estimates.json
en   192  200
pcm  171  200
ha   124  200
```

That is `k` and `n` per cell. Everything in the interval follows from those two numbers and
the published Wilson formula. Nothing about the result depends on trusting this
implementation. That is the point of recording the method beside the answer.

## A hand-assembled bundle

A directory of `items.jsonl` and a `plan.lock.json`, sealed without ever having been run,
is legitimate. `bundle` records `run_ledger: "absent"` so it says what it is rather than
passing for a run.

Use it for pooled re-analysis across several evaluations, or for reproducing published
figures from rows somebody else collected. `tests/test_estimate_credential.py` does exactly
this. It reproduces the flood-warning figures from item records, to the last bit of both
bounds.
