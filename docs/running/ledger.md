---
title: The ledger
description: >-
  The append-only run log, written at the moment of each event rather than
  assembled afterwards.
---

# The ledger

`ledger/RUNLOG.jsonl` is written as each event happens, one JSON object per line, flushed
before the next thing happens.
{ .lede }

## Why append-only, and why during

A run log a person writes afterwards is a discipline, and disciplines fail quietly. A log
assembled at the end of a run is a log that a crashed run does not have, and that is
exactly the run whose history someone will want.

So the ledger is written by the run itself, at the moment of each event, and flushed. A
process killed halfway through leaves a truthful partial record rather than nothing.

## Events

| Event | Fields |
|---|---|
| `run_started` | `plan_hash`, `plan_name`, `access_tier`, `backend`, `isolation`, `units` |
| `unit_started` | `run_id`, `image`, `seed` |
| `unit_finished` | `run_id`, `exit_code`, `image_digest`, `termination`, `egress_enforced` |
| `unit_failed` | `run_id`, `error` |
| `pack_id_overwritten` | `records` |
| `run_finished` | `items`, `failures`, `egress_enforced` |

Every line carries `utc` and `event`.

```json
{"access_tier":"black_box","backend":"docker","event":"run_started","isolation":"container","plan_hash":"81c63db1…","plan_name":"demo","units":2,"utc":"2026-08-27T09:14:02Z"}
{"event":"unit_started","image":"example_pack@sha256:…","run_id":"example_pack.r0","seed":9134…,"utc":"2026-08-27T09:14:02Z"}
{"egress_enforced":true,"event":"unit_finished","exit_code":0,"image_digest":"sha256:…","run_id":"example_pack.r0","termination":null,"utc":"2026-08-27T09:14:19Z"}
```

Keys are sorted, so two runs of the same events produce comparable bytes.

## `run_finished` is what makes a bundle sealable

`bundle` refuses to seal a run whose ledger never reached `run_finished`.

A run that failed part way through produced files that hash perfectly well and mean
nothing. Sealing them would produce a bundle that verifies and misleads, which is worse
than no bundle.

The manifest records which case it is:

| `run_ledger` | Meaning |
|---|---|
| `complete` | the ledger reached `run_finished` |
| `absent` | a directory assembled by hand |

There is deliberately **no `incomplete`**. A directory whose ledger stops before the end is
refused rather than labelled.

`absent` is legitimate. A hand-assembled bundle for re-analysis is a real thing to want,
and the field says so.

## Failures do not abort the run

A unit that fails is recorded and the run continues to the next one. The failures are
counted in `run_finished` and returned by the command, so a run where three of four units
died is a run that finished with three failures, and the ledger says which three.
