---
title: Welcome
description: >-
  Touchstone runs AI evaluations in containers, calculates the results itself,
  and creates a folder containing everything needed to verify them later.
---

# Touchstone

An open-source tool for running AI evaluations and creating evidence that anyone can check.
{ .lede }

Touchstone runs an evaluation in containers, works out every number itself rather than
taking the system's word for any of them, and writes the plan, one row per test item and a
SHA-256 of every file into a folder anyone can re-check with `shasum`.

It is built for people handed a result who have to decide whether to act on it: auditors,
procurement, risk, regulators, and the teams producing evidence for them.

!!! warning "It is not built for iterating on a prompt"

    Freezing plans and sealing bundles are overhead in a loop where you change a line and
    rerun twenty times. Use [Inspect](https://inspect.aisi.org.uk/) while exploring, and
    this for the claim you publish.

## What it does differently

**Bundles checkable without this tool.** Every file is JSON, JSON Lines or a hash. No
database, no index, no proprietary format. See [Bundle anatomy](bundles/anatomy.md).

**Every rate carries an interval.** A bare percentage cannot be represented at all. See
[Rates and Wilson](estimation/rates.md).

**Grades can say `indeterminate`** when the interval crosses a threshold, instead of
printing a letter the evidence does not support. See
[Indeterminate](scorecards/indeterminate.md).

**Packs report facts, never scores.** The arithmetic is Touchstone's, and the rows travel
in the bundle so anyone can redo it. See [Item records](components/items.md).

**Containment.** A pack reaches the hosts it declared and nothing else; the proxy that lets
it out never decrypts anything. See [Containment](running/containment.md).

**A score card is data.** Levels, thresholds and access-tier ceilings are read from a YAML
file, so a card with three levels and a card with eight both work. See
[Score card anatomy](scorecards/anatomy.md).

## The 94% problem

Two systems are tested. Both get 94%. One was tested on 50 items, the other on 1,000:

```text
94.0%  (95% CI 83.8-97.9%, n=50)     <- cannot back a claim about a 90% bar
94.0%  (95% CI 92.4-95.3%, n=1000)   <- can
```

Grades work the same way. If the error bar crosses the threshold, the honest answer is not
the better letter:

```console
headline_accuracy: indeterminate, A or C  [0.91, 0.8783 to 0.9345, n=400]
    the interval spans the A boundary of 0.9, so the grade is A or C and the evidence does not say which
```

**The interval is sampling error, and only that.** It is how far the number would move if
you drew another set of items the same way. Three larger errors are not in it: your items
are not a random sample of deployment, whatever decided `correct` has its own error rate
(correlated, not independent, when the judge is a model), and a leaked item set measures
recall rather than ability.

Two of the usual suspects *are* measured and reported next to the rate:
[between-replicate variance](estimation/replicates.md), which shows both how far the rate
moved and how many individual items flipped, and
[calibration error](estimation/calibration.md) against the system's own stated confidence.

It is precision. It is not accuracy. See [what this does not
prove](project/limits.md) for the limits a hash cannot fix.

## The pipeline

```text
validate -> freeze -> run -> estimate -> grade -> bundle -> verify
```

| Command | Does | Needs |
|---|---|---|
| [`validate`](basics/cli.md#validate) | check the plan against what each pack declares it needs | the plan and the packs |
| [`freeze`](running/freeze.md) | lock image versions, fix seeds, hash the plan | Docker |
| [`run`](running/run.md) | run the packs, write one row per test item | Docker |
| [`estimate`](estimation/rates.md) | compute rates and intervals, split by group | the bundle |
| [`grade`](scorecards/anatomy.md) | apply a score card, grade each indicator | the bundle and a card |
| [`bundle`](bundles/anatomy.md) | hash every file, write `MANIFEST.json` | the run directory |
| [`verify`](bundles/verifying.md) | re-check a bundle against its manifest, offline | the bundle |

Only `run` needs a container. Everything after it reads files, so `verify` works on a plane
with the wifi off.

## Where to start

<div class="grid cards" markdown>

- **[Installation](basics/installation.md).** `pip install touchstone-dqi`, and what needs
  Docker.
- **[Tutorial](basics/tutorial.md).** A plan through to a sealed bundle, in seven commands.
- **[Writing a pack](extending/writing-a-pack.md).** The container contract, in about
  seventy lines of standard library.
- **[What this does not prove](project/limits.md).** Read before citing anything this
  produces.

</div>

## Status

Early, and saying so. `0.4.0` is the current release, all seven commands work and are
tested doing it, and the documentation describes the code that is on PyPI. What is not settled is the
score card format. See [Status](project/status.md) and [Editor
schemas](reference/schemas.md).
