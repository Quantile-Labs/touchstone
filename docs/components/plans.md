---
title: Plans
description: >-
  The plan file, its systems, packs, access tier and seed, and what freeze does to it.
---

# Plans

A plan says what to run against what. It is the only file an analyst writes by hand to
produce a bundle, and it is what `freeze` turns into an anchor.
{ .lede }

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

Unknown keys are refused rather than ignored. A typo in a plan is a plan that does not
say what its author thought it said, and silently dropping the key is how a `replicas: 2`
becomes a single run nobody notices.

## Fields

| Field | Type | Notes |
|---|---|---|
| `plan_name` | string | Required. |
| `access_tier` | string | Required. **No claim in the report may exceed the tier declared here.** See [Tier ceilings](../scorecards/ceilings.md). |
| `seed` | integer | Optional. Materialised into the lock by `freeze`. |
| `systems` | map | Named systems under test. See [Systems](systems.md). |
| `packs` | list | The packs to run. |

### `packs[]`

| Field | Type | Notes |
|---|---|---|
| `id` | string | Required. Must match `^[a-z0-9_]{1,32}$`. Stamped onto every item record the pack produces. |
| `image` | string | Required. A tag at plan time; `freeze` resolves it to a digest. |
| `systems` | map | Maps the pack's declared input system names to systems in this plan. |
| `params` | map | Checked against the pack's `input_schema` by `validate`. |
| `replicates` | integer | Default `1`, minimum `1`. See [Replicates](../estimation/replicates.md). |

## `access_tier`

The grader enforces this as a ceiling.

An evaluation that could only see inputs and outputs cannot support a claim that needed
weights or training data, however good the numbers came out. The score card names the best
level each tier may reach, and `grade` applies it to computed and human-assessed
indicators alike.

The engine does not know what tiers exist. `black_box` and `grey_box` appear in
`examples/scorecard.yaml` because that card declares them; a card that declares four tiers
works the same way.

## `seed`

Fixed at freeze time and written into the lock, so the harness is deterministic.

!!! warning "A fixed seed does not make the system under test deterministic"

    It pins Touchstone's own sampling and the bootstrap. A hosted API can change under
    the same model name between two runs of the same frozen plan. See [What this does not
    prove](../project/limits.md).

## `replicates`

`replicates: 2` runs the whole pack twice. This is what makes run-to-run instability
measurable rather than assumed: `estimate` reports both how far the rate moved between
replicates and how many individual items flipped.

Replicates multiply the item count. `max_items: 200` with `replicates: 2` is 400 records.

## Validating

```console
$ touchstone validate examples/plan.yaml
examples/plan.yaml: ok, 1 pack(s)
```

`validate` reads each pack's `manifest.yaml` from `--manifests` (default `packs/`) and
checks the plan against it: every required input system supplied, every parameter of the
declared type, every stratum named downstream actually declared. It needs no Docker and
runs nothing.

## Freezing

```console
$ touchstone freeze examples/plan.yaml -o ./run-004
./run-004/plan.lock.json: 1 pack(s) pinned
sha256 81c63db1ae445b9ebc6d4292a4784777884efeee2cbd28be60775e7f0fafbab9
```

After this the plan is an artefact with a hash, and `run` refuses a lock that has been
edited. See [Freeze and the lock](../running/freeze.md).
