# Writing a pack

A pack is a container image that evaluates a system and reports what happened.

## Contract

1. Ship `manifest.yaml` at `/app/manifest.yaml`.
2. Accept `--systems-params` and `--test-params`, both JSON strings.
3. Write one JSON Lines record per item to `/output/items.jsonl`.
4. Exit 0 on a completed run. A non-zero exit means the run failed, not that the
   system under test scored badly.

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
reaches nothing.

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

## Summary-only packs

A pack that cannot emit items sets `emits_items: false` and writes metrics to
`/output/result.json`. Those metrics are accepted, tagged `summary_only`, carry no
interval, and are capped when graded. Use it to wrap a framework you do not control.
