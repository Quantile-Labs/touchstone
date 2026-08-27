---
title: Resource limits
description: >-
  Memory, CPU and process ceilings declared per pack, pinned into the frozen
  plan, and applied as cgroup limits.
---

# Resource limits

Each pack declares the blast radius it needs. `freeze` writes it into the plan; `run`
applies it as the container's limits.
{ .lede }

```yaml title="manifest.yaml"
resources:
  memory_mb: 4096
  cpus: 4.0
  pids: 1024
```

## Fields

| Field | Default | Minimum | Notes |
|---|---|---|---|
| `memory_mb` | `2048` | `64` | Swap is pinned to the same figure at run time. |
| `cpus` | `2.0` | `> 0` | |
| `pids` | `512` | `16` | Process count. |

Unknown keys are refused.

## Declared per pack

A global default a pack cannot express a need for is a bad ceiling: a pack that genuinely
wants 8 GB has nowhere to say so, and the operator either raises the cap for every pack at
once or not at all.

Declaring it in the manifest makes the ceiling **per pack and reviewable in the frozen
plan**. A security reviewer reads it off `plan.lock.json` instead of pulling an image to
find it.

The defaults above match what comparable harnesses apply globally, so a pack that says
nothing behaves the same.

## Swap is capped too

`memory_mb` pins swap to the same figure.

A memory cap that leaves swap open is a cap the container walks straight through. Limiting
RAM to 2 GB while leaving swap unbounded does not limit the pack; it makes it slow.

## Processes

Nothing else here caps process count, and a pack that forks in a loop takes the host down
while staying comfortably inside its memory limit. `pids` is the limit that stops it.

## Being killed is recorded

A pack killed by the memory cgroup is recorded as `out_of_memory`:

```json
{"utc": "...", "event": "unit_finished", "run_id": "example_pack.r0",
 "exit_code": 137, "termination": "out_of_memory", "egress_enforced": true}
```

Docker reports 137 for a killed container, and that is also what a timeout reports, so the
exit code alone cannot tell them apart. `termination` is carried separately for exactly
this reason. See [Running packs](run.md#termination-is-recorded-separately-from-the-exit-code).

The harness knows a timeout because its own wait expired, and reads a 137 that arrives any
other way as the memory cap, which every container runs under. Docker's `State.OOMKilled`
is not what decides it: dockerd writes that flag from an event containerd delivers, on
cgroup v2 the event is sometimes never delivered, and a container the kernel killed would
then be recorded as a pack that chose to exit 137. The cost of reading the exit code
instead is that a pack calling `exit(137)` on purpose is filed as killed for memory, which
is the safer of the two mistakes: it names the harness rather than the system under test.
