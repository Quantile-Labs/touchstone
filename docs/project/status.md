---
title: Status
description: What is settled in 0.1.0, what is not, and what is planned.
---

# Status

Early, and saying so.
{ .lede }

## 0.1.0

The first release that is the code this documentation describes. All seven commands work
and are tested doing it.

```console
$ touchstone version
touchstone 0.1.0
```

Classified `Development Status :: 2 - Pre-Alpha` on PyPI, which is accurate.

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
