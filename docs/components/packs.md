---
title: Packs
description: >-
  What a pack is, what it declares in its manifest, and where it sits between the
  plan and the item records.
---

# Packs

A pack is a container image that evaluates a system and reports what happened. It is the
only part of the pipeline that talks to the system under test.
{ .lede }

Touchstone runs it, contains it, and does arithmetic on the rows it emits. It never asks
the pack for a score. See [Item records](items.md) for why.

To write one, see [Writing a pack](../extending/writing-a-pack.md). This page covers what
a pack *is* from the plan's side.

## The manifest

Every pack ships `manifest.yaml` at `/app/manifest.yaml`. It is read before the pack runs,
by `validate` from disk and by `freeze` out of the image, so a plan can be checked against
what the pack actually needs.

```yaml title="packs/example_pack/manifest.yaml"
name: "example_pack"
version: "1.0"
description: "Minimal pack used by the test suite and as a template."

input_systems:
  - name: "system_under_test"
    type: "llm_api"
    required: true

input_schema:
  - name: "max_items"
    type: "integer"
    required: false
    description: "How many records to emit. Ten by default."

emits_items: true
calibrates: "correct"

strata:
  - name: "language"
    values: ["en", "pcm", "ha", "yo", "ig"]
  - name: "difficulty"
    values: ["single_step", "multi_step"]

network:
  egress: []
```

Unknown keys are refused.

## Fields

| Field | Type | Notes |
|---|---|---|
| `name` | string | Required. |
| `version` | string | Required. |
| `description` | string | Optional. |
| `input_systems` | list | Systems this pack needs. See [Systems](systems.md). |
| `input_schema` | list | Parameters the plan may pass. Checked by `validate`. |
| `emits_items` | bool | Default `true`. `false` is [summary-only](../extending/writing-a-pack.md#summary-only-packs). |
| `locale` | list of string | Informational. **The engine never branches on it.** |
| `strata` | list | Dimensions the pack tags items with. See [Strata](../estimation/strata.md). |
| `network` | object | `egress`, the hosts this pack may reach. See [Containment](../running/containment.md). |
| `resources` | object | Memory, CPU and process ceilings. See [Resource limits](../running/limits.md). |
| `calibrates` | string | Which outcome `confidence` is a claim about. See [Calibration](../estimation/calibration.md). |

## Declarations are enforced

Three of these are enforced rather than documented:

**`network.egress`** is what the container actually gets. Empty means no network at all.
See [Containment](../running/containment.md).

**`resources`** becomes the container's cgroup limits, written into the frozen plan where a
reviewer can read them. See [Resource limits](../running/limits.md).

**`calibrates`** is pinned into the lock by `freeze`, so what was calibrated is part of the
frozen plan rather than a choice someone made after seeing the numbers.

## `strata`

```yaml
strata:
  - name: "language"
    values: ["en", "pcm", "ha", "yo", "ig"]
```

Declared so a plan and a score card can be checked against it before anything runs. A
`worst_stratum` indicator naming a key no pack emits is a mistake worth catching at
`validate`, while nothing has yet been spent on running it.

**The values are yours.** Touchstone never interprets them, which is why a pack for any
market works without a change to the engine.

## `emits_items: false`

A pack that cannot emit per-item rows, because it wraps a framework you do not control,
sets this and writes metrics to `/output/result.json` instead.

Those metrics are accepted, tagged `summary_only`, **carry no interval**, and are capped
when graded by the card's `summary_only_ceiling`. The cap follows from nobody being able
to check them.

## Provenance

`freeze` resolves each `image:` tag to a digest and records it in `plan.lock.json`, along
with the manifest it read out of that image. The pack that ran is identified in the bundle
by content, not by name.

!!! warning "A pinned image is not a pinned system"

    `freeze` pins the code that does the asking. The system being asked is often a hosted
    API, and there is no digest for somebody else's endpoint. See [What this does not
    prove](../project/limits.md).
