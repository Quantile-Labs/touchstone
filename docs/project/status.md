---
title: Status
description: What is settled in 0.2.1, what is not, and what is planned.
---

# Status

Early, and saying so.
{ .lede }

## 0.2.1

A container the kernel kills for exceeding its memory cap is recorded as `out_of_memory`
from its exit code. `State.OOMKilled`, which decided it before, is written from an event
containerd delivers and on cgroup v2 that event is sometimes never delivered, so a run the
harness starved could reach a bundle looking like the pack's own exit code. See [Resource
limits](../running/limits.md#being-killed-is-recorded).

```console
$ touchstone version
touchstone 0.2.1
```

Still classified `Development Status :: 2 - Pre-Alpha` on PyPI, which is accurate.

## 0.2.0

`estimate` given more than one `--by` key rolls up each key on its own as well as crossing
them, so a card that asks about one dimension per indicator reads its cells off a single
run. `grade` refuses a worst stratum that names no keys where the bundle holds cells
sitting inside other cells, rather than ranking a group against part of itself.

## 0.1.0

The first release that is the code this documentation describes. All seven commands work
and are tested doing it.

## What is settled

- **The bundle format.** `MANIFEST.json`, the hash over the canonical file list, and the
  refusal to seal an incomplete ledger.
- **The item record.** One row per item, no scores, `pack_id` stamped by the harness.
- **The statistics.** Wilson for rates, seeded BCa for scores, ECE against a declared
  outcome, between-replicate variance. The arithmetic is pinned by tests.
- **Containment.** Internal network, proxy sidecar, no TLS termination, declared hosts only.
- **The pack contract.** `manifest.yaml` at `/app`, results to `/output`, stdout is logs.

## What is not settled

!!! warning "The score card format"

    `grade` applies whatever ladder the card gives it rather than one built in, and
    `examples/scorecard.yaml` shows the shape rather than a rubric anyone should adopt.

    The condition vocabulary, the shape of `MetricRef`, and how per-indicator ceilings are
    expressed may all change. If you are writing cards now, expect to migrate them.

The package is `touchstone-dqi` because `touchstone` was taken on PyPI. **DQI** is the
deployment quality index this is being built to carry, which is separate work and is not
published, so nothing here grades against it.

## Known gaps

| Gap | Notes |
|---|---|
| `example_pack` is not published | Every hash in the tutorial is specific to the machine that built the image. |
| No backend registration | A third-party [backend](../extending/backends.md) means a fork. A plugin entry point is planned. |
| One backend | `docker` only. |
| No trace viewer | `trace_ref` points into the bundle; reading it is your text editor's job. |
| Anchors need manual upgrade | `ots upgrade` is a step somebody has to remember. See [Anchoring](../bundles/anchoring.md). |

## Bundles sealed before 0.2.1

A bundle from 0.1.0 or 0.2.0 verifies exactly as it did. Two things in one are worth
knowing before quoting what it says.

| Sealed by | Reads |
|---|---|
| 0.1.0 | `touchstone_version` says `0.0.1`. That release bumped `pyproject.toml` and left the string the code stamps, so a bundle reading `0.0.1` came from 0.0.1 or from 0.1.0. |
| 0.1.0 or 0.2.0 | A unit the kernel killed for exceeding its memory cap can carry `exit_code: 137` with `termination` null, which reads as the pack exiting 137 on its own. See [Resource limits](../running/limits.md#being-killed-is-recorded). |

Neither touches a hash, and neither can be corrected in a bundle that is already sealed.
Re-running under 0.2.1 is what settles a 137 in an old one.

## What is tested

```bash
uv run pytest -q
```

Some of it is worth naming, because it is the kind of testing that decides whether the
claims on this site hold:

- **The offline claim.** CI installs the package with the network switched off and runs it,
  on every change.
- **The published figures.** `tests/test_estimate_credential.py` reproduces the
  flood-warning numbers from item records, to the last bit of both bounds.
- **The bootstrap arithmetic.** Pinned to fixed values, so a Python upgrade that moved an
  interval fails the build rather than the client.
- **This documentation.** The console blocks in the README are executed, and every command
  in the pipeline table is checked to exist.

## Versioning

No stability guarantee before 1.0. The `lock_format` and `bundle_format` integers are how a
format change announces itself; a bump changes the hash of an unchanged plan, which is the
point.
