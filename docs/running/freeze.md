---
title: Freeze and the lock
description: >-
  What freeze pins, why the lock is canonical JSON, and how a plan hash keeps a
  grade boundary from moving after the result is known.
---

# Freeze and the lock

`freeze` turns a plan into an artefact with a hash: every image resolved to a digest, every
seed materialised, every declaration read out of the image and pinned.
{ .lede }

```console
$ touchstone freeze examples/plan.yaml -o ./run-004
./run-004/plan.lock.json: 1 pack(s) pinned
sha256 81c63db1ae445b9ebc6d4292a4784777884efeee2cbd28be60775e7f0fafbab9
```

Two files come out: `plan.lock.json` and `PLAN.sha256`.

## What it is for

A grade boundary only constrains anything if it was fixed before the result was known.
Freezing first, then running, fixes the threshold and the number in that order, and the
hash is what lets a reader check the order held.

`run` refuses a lock that was never frozen or has been edited since.

## What gets pinned

| Pinned | From | Why |
|---|---|---|
| `image` | the registry | A digest, not a tag. `example_pack:1.0` can be repointed; `@sha256:…` cannot. |
| `seeds` | derived | One per pack per replicate. |
| `egress` | the pack's manifest | So a **security review reads the frozen plan** rather than pulling an image. |
| `resources` | the pack's manifest | So the ceiling is reviewable in the same place. |
| `calibrates` | the pack's manifest | So what was calibrated is part of the frozen plan, not a flag someone typed after. |
| `emits_items` | the pack's manifest | So a sealed bundle can tell a rate computed from items apart from one a container asserted. |

A pack with no manifest in its image cannot be frozen. What the pack may reach would be
unpinnable, leaving a security reviewer nothing to read off the frozen plan.

## Seeds

One root seed becomes one seed per pack per replicate, by SHA-256 so any language agrees on
the derivation:

```python
seed = int.from_bytes(
    hashlib.sha256(f"{root_seed}:{pack_id}:{replicate}".encode()).digest()[:8], "big"
)
```

Recorded in the lock, so a rerun matches rather than being asserted to.

## Why the lock is canonical JSON

The lock is written as canonical JSON rather than YAML so one file carries both properties
the anchor needs:

- `shasum -a 256 -c PLAN.sha256` checks it with no tooling at all.
- The bytes are derivable from the plan data in any language.

Hashing a YAML rendering would give the first and lose the second.

## The lock holds no timestamp

`PlanLock` records plan content only. No timestamp, no tool version. Freezing the same plan
twice produces the same bytes and therefore the same hash.

When it was frozen is an *event*, and events belong in [the ledger](ledger.md).

## `lock_format`

```json
{"lock_format": 4, "plan_name": "demo", "access_tier": "black_box", ...}
```

A format bump changes the bytes and therefore the hash of an unchanged plan. That is
deliberate: a lock read under different rules is a different lock.

Format 2 added `calibrates`, 3 added `emits_items`, 4 added `resources`.

## Anchoring

```console
$ touchstone freeze examples/plan.yaml -o ./run-004 --anchor
```

Stamps the plan hash with OpenTimestamps, proving the plan existed before the run. Needs
network. See [Anchoring](../bundles/anchoring.md).
