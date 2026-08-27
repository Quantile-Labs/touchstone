---
title: Running packs
description: >-
  How run executes a frozen plan, what a unit is, and how a non-zero exit is
  recorded rather than swallowed.
---

# Running packs

```console
$ touchstone run ./run-004 -o ./run-004
```

`run` executes a frozen plan. It refuses one that was never frozen or has been edited.
{ .lede }

**Needs Docker.** It is one of two commands that do.

## Units

The unit of work is **one pack at one replicate**, the thing that either ran or did not.

A plan with two packs, one at `replicates: 3` and one at `replicates: 1`, is four units.
Each gets its own `run_id`, its own seed, its own container and its own output directory
under `runs/`.

```text
run-004/runs/
├── example_pack.r0/
│   └── items.jsonl
└── example_pack.r1/
    └── items.jsonl
```

Those are merged into the bundle's top-level `items.jsonl`. The per-unit files stay, so the
merge is checkable.

## `pack_id` is stamped at merge

When the per-unit files are merged, the harness writes `pack_id` onto every record and
**overwrites anything the pack put there**. If it overwrote any, the ledger records it:

```json
{"utc": "...", "event": "pack_id_overwritten", "records": 12}
```

That line is a finding about the pack, not an error in the run. See [Item
records](../components/items.md#pack_id-is-written-by-the-harness).

## What a non-zero exit means

```text
exit 0        the pack completed
exit non-zero the run failed
```

A pack that finds the system under test is terrible still exits 0. It reports the failure
in the rows.

The distinction matters because a pack that crashes produces files that hash perfectly well
and mean nothing. `bundle` refuses to seal a run whose ledger never reached `run_finished`.

## Termination is recorded separately from the exit code

Both Docker and a timeout report exit 137, which is also plain SIGKILL. An exit code alone
cannot tell them apart, so `RunResult` carries `termination` beside it:

| `termination` | Meaning |
|---|---|
| `null` | exited on its own |
| `out_of_memory` | killed by the memory cgroup |
| `timeout` | killed by the harness for taking too long |
| `cancelled` | stopped deliberately |

A pack killed for memory is recorded as `out_of_memory`, not as a timeout. See [Resource
limits](limits.md).

## What run writes

| File | Contents |
|---|---|
| `runs/<run_id>/items.jsonl` | the rows one unit produced, untouched |
| `runs/<run_id>.egress.log` | every request that unit made, allowed or denied |
| `items.jsonl` | all units merged, `pack_id` stamped |
| `environment.json` | what it ran on, and whether egress was enforced |
| `ledger/RUNLOG.jsonl` | append-only, written as each event happened |
| `plan.lock.json`, `PLAN.sha256` | copied from the lock directory |

## `environment.json`

```json
{
  "touchstone_version": "0.2.0",
  "python": "3.12.4",
  "platform": "Linux-6.8.0-x86_64",
  "backend": "docker",
  "isolation": "container",
  "plan_hash": "81c63db1…",
  "image_digests": ["example_pack@sha256:…"],
  "egress_enforced": true
}
```

`image_digests` is read back from the runtime, so it holds the images that *actually ran*
rather than the ones the lock asked for. `isolation` is what the backend could actually provide: a runtime
that contained the pack less well than a container says so here, machine-readably, because
that is the access-tier argument applied to the runtime.

`egress_enforced` is across the whole run. It is `false` if **any** unit was granted a
network it declared but the backend could not restrict. A claim that a pack was contained
is not available then. See [Containment](containment.md).
