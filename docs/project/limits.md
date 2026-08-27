---
title: What this does not prove
description: >-
  The limits a hash cannot fix: run selection, unpinnable endpoints, and what an interval
  leaves out.
---

# What this does not prove

Read this before citing anything the pipeline produces.
{ .lede }

## Nothing stops someone running it ten times and sealing the run they liked

**Run selection leaves no trace in any artefact this tool produces.**

Each of the ten runs would freeze, run, seal and verify perfectly. Nine would be deleted.
The tenth would be published with a valid manifest, a matching plan hash, and an anchor
proving the plan predated it. Every one of those checks would pass, because every one of
them is true.

Closing this takes a **commitment made in advance to publish every run against a plan**,
which is a process somebody keeps and not something `shasum` checks. If you are relying on
a bundle somebody else produced, that commitment, and whether anyone audits it, is the
question to ask. The tooling cannot answer it for you.

## A pinned image is not a pinned system

`freeze` pins the code that does the asking.

The system being asked is often a hosted API, and **there is no digest for somebody else's
endpoint**: it can change under the same model name between two runs of the same frozen
plan. The vendor is not obliged to tell you, and usually does not.

Fixed seeds make the harness deterministic, not the system under test. [Replicates](../estimation/replicates.md)
measure some of the resulting variation; they do not measure a change that happened between
your evaluation and someone's deployment.

## The interval is sampling error, and only that

It is how far the number would move if you drew another set of items the same way.

Three larger errors are **not** in it:

1. **Your items are not a random sample of deployment.** Whatever process produced the item
   set has a composition, and the interval assumes that composition is the one you care
   about. It usually is not.
2. **Whatever decided `correct` has its own error rate**, and that error is correlated
   with the item when the judge is a model. A judge that systematically misreads one kind of
   answer moves the rate without widening the interval at all.
3. **A leaked item set measures recall rather than ability.** If the items are in the
   training data, the number is real and means something entirely different from what it
   appears to mean.

Two of the usual suspects *are* measured and reported next to the rate:
[between-replicate variance](../estimation/replicates.md) and [calibration
error](../estimation/calibration.md).

**It is precision. It is not accuracy.**

## A grade is not an approval

Touchstone is not a benchmark, a leaderboard, a safety test or a certificate.

A grade says what the evidence supports. Nothing in it amounts to an approval, and nothing
in it transfers responsibility for a deployment decision from the person making it to the
tool.

## The score card is somebody's judgment

The [engine has no rubric](../scorecards/anatomy.md#the-engine-has-no-rubric). Levels,
thresholds and ceilings come from a YAML file, which means the grade is only as defensible
as that file.

`examples/scorecard.yaml` is **not a standard.** Its numbers are invented to show the shape
of the format. What counts as fit for service is a policy judgment about acceptable harm in
a named use case.

## What it does prove

Worth being equally plain about, since the list above is long:

- The files have not changed since sealing.
- The arithmetic on those files is correct, and can be redone without this tool.
- The thresholds were fixed before the run, if the plan was anchored and the anchor
  upgraded.
- The pack reached the hosts it declared and no others, if `egress_enforced` is `true`.
- The rate came from `n` observations, and the interval is what that `n` supports.

That is a narrower claim than "this system is safe". It is also a claim nobody currently
has to take on trust, which is the trade the format is making.
