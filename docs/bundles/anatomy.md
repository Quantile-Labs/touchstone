---
title: Bundle anatomy
description: >-
  What a sealed evidence bundle contains, how the manifest hash is computed, and
  why it is all plain files.
---

# Bundle anatomy

A bundle is a folder. 204 KB for the tutorial run. It should still make sense after
Touchstone is gone.
{ .lede }

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

Also present when they apply: `audit.yaml` ([audit responses](../scorecards/audit.md)),
`anchors/` ([anchoring](anchoring.md)), `runs/<run_id>.egress.log`
([containment](../running/containment.md)).

## Every file is JSON, JSON Lines or a hash

No database, no index, no proprietary format. This is the whole argument of the format.

A bundle is handed to an auditor, a regulator, a procurement team, or somebody's lawyer
three years after the run. Any of them can open it with a text editor. None of them should
have to install a Python package to find out what it says. If the only reader is this tool,
the evidence is only as durable as this tool.

## Sealing

```console
$ touchstone bundle ./run-004
./run-004: sealed 9 file(s)
sha256 dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba
```

## `MANIFEST.json`

```json
{
  "bundle_format": 1,
  "touchstone_version": "0.1.0",
  "sealed_utc": "2026-08-27T09:21:44Z",
  "run_ledger": "complete",
  "sha256": "dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba",
  "files": [
    {"path": "PLAN.sha256", "size": 77, "sha256": "…"},
    {"path": "environment.json", "size": 412, "sha256": "…"},
    {"path": "estimates.json", "size": 18244, "sha256": "…"},
    {"path": "items.jsonl", "size": 168290, "sha256": "fc127dc53abc…"},
    {"path": "ledger/RUNLOG.jsonl", "size": 1104, "sha256": "…"}
  ]
}
```

Paths are relative to the bundle root, forward slashes on every platform. A path that
starts with `/` or contains `..` is refused. A manifest lists things inside the bundle, and
one that reaches outside is either a mistake or an attack.

## The bundle hash

`sha256` is over **the canonicalised file list alone**, not over `MANIFEST.json` as a file:

```python
hashlib.sha256(
    json.dumps(
        [entry.model_dump() for entry in files],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
).hexdigest()
```

So it does not move when `sealed_utc` does, and it is independent of how `MANIFEST.json`
itself is formatted. **This is the one value a report quotes and an anchor timestamps.**

You can recompute it with `jq` and `shasum`:

```console
$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba  -
```

## `run_ledger`

| Value | Meaning |
|---|---|
| `complete` | the ledger reached `run_finished` |
| `absent` | a directory assembled by hand |

There is deliberately **no `incomplete`**. A run that stopped part way produced files that
hash perfectly well and mean nothing, and `bundle` refuses to seal it rather than labelling
it.

`absent` is legitimate. A hand-assembled bundle for re-analysis is a real thing to want,
and the field says so. See [The ledger](../running/ledger.md).

## `bundle_format`

Bumped when the layout changes in a way an older `verify` cannot read. Currently `1`.

## What each file is for

| File | Read it for |
|---|---|
| `plan.lock.json` | what was run: image digests, seeds, declared egress, resource ceilings, access tier |
| `PLAN.sha256` | the plan hash on its own, checkable with `shasum -c` |
| `environment.json` | what it ran on, and whether egress was enforced |
| `items.jsonl` | the observations. Everything else is derived from this |
| `estimates.json` | the rates, with method, parameters and citation beside each |
| `scorecard.json` | the grades, the rules that decided them, and the ceilings that bit |
| `ledger/RUNLOG.jsonl` | what happened, in order, as it happened |
| `runs/` | the per-unit files before merging, so the merge is checkable |

## Where to go next

- [Verifying a bundle](verifying.md), with and without this tool.
- [Re-analysis](reanalysis.md), recomputing from `items.jsonl`.
- [Anchoring](anchoring.md), proving the plan existed before the run.
