---
title: Writing a pack
description: >-
  The container contract, covering the manifest, the arguments and the item records, and
  the rules that keep a pack from being trusted with the arithmetic.
---

# Writing a pack

A pack is a container image that evaluates a system and reports what happened.
{ .lede }

It is the only part of the pipeline that talks to the system under test. See
[Packs](../components/packs.md) for what a pack looks like from the plan's side, and
[Item records](../components/items.md) for the record format in detail.

## Contract

1. Ship `manifest.yaml` at `/app/manifest.yaml`.
2. Accept `--systems-params` and `--test-params`, both JSON strings.
3. Write one JSON Lines record per item to `/output/items.jsonl`.
4. Exit 0 on a completed run. A non-zero exit means the run failed, not that the
   system under test scored badly.
5. Accept `--output-dir`, defaulting to `/output`. This is what lets a pack author run
   the pack outside a container while writing it.

!!! warning "The container runs as the user who invoked Touchstone"

    Not as root, and not as the image's `USER`. A bind mount on Linux keeps host
    ownership, so a pack running as anyone else cannot write to `/output`. Do not put a
    `USER` line in your Dockerfile expecting it to apply.

!!! danger "Results go in `/output`, never to stdout"

    Stdout is logs. It is not captured into the bundle, and a pack that prints a request
    prints the credential with it.

`packs/example_pack/` is a working pack that follows all of this in about seventy lines of
standard library. Copy it.

## Manifest

```yaml
name: "example_pack"
version: "1.0"
description: "What this measures."

input_systems:
  - name: "system_under_test"
    type: "llm_api"
    required: true

input_schema:
  - name: "max_items"
    type: "integer"
    required: false

emits_items: true

strata:
  - name: "language"
    values: ["en", "pcm", "ha", "yo", "ig"]

network:
  egress: ["api.openai.com"]
```

`network.egress` is a declaration a security reviewer can read. Empty means the pack
reaches nothing, and that is enforced: the container runs with no network at all.

**A non-empty allowlist is enforced.** The pack runs on a Docker network created
`--internal`, which has no route off the host, and a squid sidecar attached to both that
network and the bridge is the only way through. It allows `CONNECT` to the declared hosts
and denies everything else.

**Containment does not depend on your pack.** It is told about the proxy through
`HTTPS_PROXY` and the usual spellings, and that is a courtesy rather than the control: a
pack that ignores those variables is on a network with nowhere to go. The internal network
is what makes the answer irrelevant.

**The proxy never terminates TLS.** It reads the hostname off the `CONNECT` line and the
bytes stay opaque, so it is never trusted with your API keys. That is the constraint the
design is built around rather than a limitation of it.

Declare hostnames and nothing else. No scheme, no port, no path, no wildcard, and no bare
IP address: `dstdomain` matches names rather than addresses, so an address would be
accepted and then match nothing, and a denial with no explanation is worse than a refusal
with one. A host that is not a hostname is refused before anything starts. `dstdomain
example.com` matches that host and not its subdomains, so a pack that needs a subdomain
declares the subdomain.

The bundle records what happened. `environment.json` carries `egress_enforced: true`, and
every request the pack made, allowed or denied, is written to `<run_id>.egress.log` beside
its records. **A denial in there is a finding rather than an error**: it says the pack
tried to reach a host it never declared.

`--allow-unenforced-egress` is a downgrade of something the backend can now do. It runs the
pack on the ordinary bridge network with the whole internet available, and records
`egress_enforced: false` so a reader knows the pack was not contained. Use it to develop
against a real API. It is not a way to produce evidence for anyone.

`strata` is declared so a plan can be checked against it before anything runs. The
values are yours. Touchstone never interprets them, which is why a pack for any
market works without a change to the engine.

## Item records

```json
{"item_id": "example.001", "stratum": {"language": "pcm"}, "outcome": {"correct": true}}
```

| Field | Purpose |
|---|---|
| `item_id` | stable across runs, joins re-analyses together |
| `stratum` | free-form dimensions, grouped by the estimator |
| `outcome` | booleans, become rates with a denominator |
| `score` | continuous measures, become means with intervals |
| `confidence` | optional, enables calibration and confident-and-wrong |
| `cost` | tokens, latency |
| `trace_ref` | path to the full prompt and response |
| `replicate` | which repeat this is |

Emit the observation, not the average. Touchstone computes every statistic from these
records so that a reader can recompute them from the bundle without trusting the pack.
`touchstone estimate` turns booleans into rates with a Wilson interval and scores into
means with a BCa bootstrap interval, grouped by whichever `stratum` keys are asked for.

A `confidence` is a claim about one particular outcome, and only the pack knows which, so
the manifest names it:

```yaml
calibrates: "correct"
```

`freeze` reads that from the image and pins it into the lock, so what was calibrated is
part of the frozen plan. A pack that declares nothing is never calibrated, because an ECE
binned against an unrelated boolean is a meaningless number that reads as an authoritative
one. `estimate --calibrate <outcome>` overrides the declaration for re-analysis.

Do not emit `pack_id` on a record. The harness stamps it when it merges the per-unit files
and overwrites anything found there: a pack that could name itself could name another one,
and every rate downstream is grouped by that field.

## Summary-only packs

A pack that cannot emit items sets `emits_items: false` and writes metrics to
`/output/result.json`. Those metrics are accepted, tagged `summary_only`, carry no
interval, and are capped when graded. Use it to wrap a framework you do not control.
