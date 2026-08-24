# Touchstone

Touchstone runs an evaluation against an AI system and produces a sealed evidence
bundle: the frozen plan, the per-item observations, the estimates with intervals, and
a hash over every byte. Anyone can re-check the result offline without trusting the
party that produced it.

**Status: early. The contracts are settling and the commands below are the ones that
work today.** See [Roadmap](#roadmap).

## Why it exists

Most evaluation tools report a number. A number is enough to decide whether to ship.
It is not enough to defend a claim to a regulator, an auditor or a hostile reviewer
eighteen months later, because by then the model has changed, the tag has moved and
the sample is gone.

Touchstone makes three choices that follow from that:

- **Packs emit observations, not statistics.** One record per item, with its strata.
  Touchstone computes every rate, interval and breakdown, so the aggregate is a
  function of a sample that ships inside the bundle.
- **Runs are pinned before they start.** `freeze` resolves every image tag to a
  digest, hashes the plan and fixes the thresholds. `run` refuses an unfrozen plan.
- **Everything after `run` is a pure function over files.** No database, no network.
  It works on a laptop with the wifi off.

## Requirements

- Python 3.12 or later
- Docker, for running packs. Not needed for `validate` or `verify`.

## Install

```bash
pip install touchstone-dqi
```

## Use

Check a plan without running anything:

```bash
touchstone validate plan.yaml
```

Verify a bundle someone sent you. No network, no Docker, no config:

```bash
touchstone verify ./bundle
```

Exit code 0 means every file matches the hash recorded in `MANIFEST.json`. Exit code 1
means it does not, and the output says which file.

## The pipeline

```
validate -> freeze -> run -> estimate -> grade -> bundle -> verify
```

| Command | Does | Needs Docker |
|---|---|---|
| `validate` | check the plan against pack manifests | no |
| `freeze` | pin digests, hash the plan, fix seeds and thresholds | no |
| `run` | execute packs, write per-item observations | yes |
| `estimate` | compute rates and intervals, by stratum | no |
| `grade` | apply a score card, produce DQI indicators | no |
| `bundle` | seal and hash the output | no |
| `verify` | re-check a bundle, offline | no |

## Writing a pack

A pack is a container image with a `manifest.yaml` at `/app/manifest.yaml` declaring
what it needs and what it emits. It writes one JSON Lines record per item to
`/output/items.jsonl`:

```json
{
  "item_id": "procedural.0417",
  "stratum": {"language": "pcm", "difficulty": "multi_step"},
  "outcome": {"correct": false},
  "confidence": 0.94
}
```

Touchstone does the rest. See [docs/packs.md](docs/packs.md).

## Roadmap

| Milestone | State |
|---|---|
| Contracts, `validate`, `verify` | in progress |
| `freeze`: digest pinning, plan hash, seeds | next |
| `run`: Docker backend, resumable journal | next |
| `estimate`: Wilson intervals, stratified rollup | after that |
| `grade`, `bundle`, report rendering | after that |

## Licence

Apache 2.0. See [LICENSE](LICENSE).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. The commit message and code style rules
are enforced by CI.

Maintained by [Quantile Labs](https://quantilelabs.com).
