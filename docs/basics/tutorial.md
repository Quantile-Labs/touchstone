---
title: Tutorial
description: >-
  A plan through to a sealed evidence bundle in seven commands, using the example
  pack that ships with the repository.
---

# Tutorial

Seven commands take a plan to a sealed bundle. This walks through all of them using
`example_pack`, which ships with the repository.
{ .lede }

!!! warning "The hashes below are specific to the machine that made them"

    `example_pack` is not published to a registry yet, so the image digest, and every
    hash that follows from it, will differ on yours until it is. The commands themselves
    run.

## Build the pack

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
docker build -t example_pack:1.0 packs/example_pack
```

## The plan

A plan says what to run against what. This is `examples/plan.yaml`, whole:

```yaml title="examples/plan.yaml"
plan_name: "demo"
access_tier: "black_box"
seed: 7

systems:
  chatbot:
    type: "llm_api"

packs:
  - id: "example_pack"
    image: "example_pack:1.0"
    systems:
      system_under_test: "chatbot"
    params:
      max_items: 200
    replicates: 2
```

Three things there are worth naming now.

`access_tier` caps what any grade may later claim. A black-box evaluation cannot reach a
level that only weights-access evidence could support, however good the numbers are. See
[Tier ceilings](../scorecards/ceilings.md).

`replicates: 2` runs the whole thing twice, which makes run-to-run instability measurable
rather than assumed. See [Replicates](../estimation/replicates.md).

`max_items: 200` over two replicates is 400 records, which is enough for a language cell to
clear the minimum size a [worst-stratum](../estimation/strata.md) indicator should accept.

Full field reference: [Plans](../components/plans.md).

## 1. `validate`

Checks the plan against what each pack declares it needs, before anything runs.

```console
$ touchstone validate examples/plan.yaml
examples/plan.yaml: ok, 1 pack(s)
```

It reads each pack's `manifest.yaml` and confirms the plan supplies the systems it
requires, that the parameters are the types it declared, and that any strata named
downstream actually exist. No Docker.

## 2. `freeze`

```console
$ touchstone freeze examples/plan.yaml -o ./run-004
./run-004/plan.lock.json: 1 pack(s) pinned
sha256 81c63db1ae445b9ebc6d4292a4784777884efeee2cbd28be60775e7f0fafbab9
```

`freeze` locks each image to a digest, fixes the seeds and hashes the plan, so a grade
boundary cannot be moved after seeing the result without it showing. See [Freeze and the
lock](../running/freeze.md).

## 3. `run`

```console
$ touchstone run ./run-004 -o ./run-004
```

Each pack runs in a container, on a network with no route out unless it declared hosts, and
writes one JSON Lines record per test item. Nothing here computes a score. See [Running
packs](../running/run.md) and [Containment](../running/containment.md).

## 4. `estimate`

```console
$ touchstone estimate ./run-004 --by language
```

True/false answers become rates with a Wilson interval; scores become means with a seeded
bootstrap. `--by` splits by any group the pack declared.

Here is what it looks like against a real item set. A flood warning system was asked, for each
of 6,772 river locations, whether it could show evidence of coverage:

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

`estimates.json` records the method and its settings next to every number, so the sums can
be redone in R, in a spreadsheet or on paper. This step needs no Docker, no database and no
network. See [Rates and Wilson](../estimation/rates.md).

## 5. `grade`

```console
$ touchstone grade ./run-004 --score-card examples/scorecard.yaml
```

A score card is the rubric, as data: the ladder, the thresholds and the ceilings are all
read from the file. The engine has no rubric of its own. See [Score card
anatomy](../scorecards/anatomy.md).

## 6. `bundle`

```console
$ touchstone bundle ./run-004
./run-004: sealed 9 file(s)
sha256 dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba
```

Hashes every file and writes `MANIFEST.json`. See [Bundle
anatomy](../bundles/anatomy.md).

## 7. `verify`

```console
$ touchstone verify ./run-004
./run-004: verified
```

Walks every file in the manifest and exits non-zero on the first mismatch. Offline. See
[Verifying a bundle](../bundles/verifying.md).

## What you have now

A folder, 204 KB for the run above, that should still make sense after Touchstone is gone:

```text
run-004/
├── MANIFEST.json        every file below, with its SHA-256 and size
├── PLAN.sha256          the plan hash, checkable with shasum alone
├── plan.lock.json       image digests, seeds, declared egress, resource ceilings
├── environment.json     what it ran on, and whether egress was enforced
├── items.jsonl          one row per test item, stamped with the pack that produced it
├── estimates.json       every rate with its interval, method, parameters, denominator
├── scorecard.json       the grade each indicator got, and what decided it
├── ledger/RUNLOG.jsonl  append-only, written as each event happened
└── runs/                the per-unit item files, before merging
```

You do not need Touchstone to check it:

```console
$ shasum -a 256 run-004/items.jsonl
fc127dc53abc97b4528d666a732707ca5b010dd108713ad830e540e0d3d932b0  run-004/items.jsonl

$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba  -
```

## Next

- [What this does not prove](../project/limits.md). Read this before citing anything the
  pipeline produces.
- [Writing a pack](../extending/writing-a-pack.md), to evaluate your own system.
- [Score card anatomy](../scorecards/anatomy.md), to write your own rubric.
