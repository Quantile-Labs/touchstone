# Touchstone

**Evaluation runs that produce evidence a stranger can re-check.**

Touchstone runs your evaluation packs in containers, computes the statistics itself, and
seals everything into a bundle: the frozen plan, every per-item observation, and a SHA-256
over every file. Anyone can re-check that bundle offline, without this tool, and without
trusting whoever produced it.

## Why

Most evaluation tooling reports a rate. A rate on its own cannot be checked.

```
47 of 50    →  94%
940 of 1000 →  94%
```

Same number, and only one of them supports a claim about a 90% bar. Touchstone cannot
print a bare proportion, because the type that carries a result has nowhere to put one:

```
94.0%  (95% CI 83.5-98.8%, n=50)     ← cannot support the claim
94.0%  (95% CI 92.4-95.4%, n=1000)   ← can
```

The same idea decides grades. A score card asserts a level when a metric clears a
threshold, and where the interval spans that threshold the honest answer is not the better
level:

```console
headline_accuracy: indeterminate, A or C  [0.91, 0.8783 to 0.9345, n=400]
    the interval spans the A boundary of 0.9, so the grade is A or C and the evidence does not say which
worst_stratum: indeterminate, A or B  [0.861, 0.803 to 0.905, n=180, language=pcm]
```

Grading the point estimate would have printed two confident letters. Both are better than
this evaluation can support.

## Quickstart

```bash
pip install touchstone-dqi
```

```console
$ touchstone validate examples/plan.yaml
examples/plan.yaml: ok, 1 pack(s)

$ touchstone freeze examples/plan.yaml -o ./run-004
./run-004/plan.lock.json: 1 pack(s) pinned
sha256 d1f2714d732b1392cca83a1e36e7bca683da6cd1557a112c823183f6a093b9c7
check it with: shasum -a 256 -c run-004/PLAN.sha256

$ touchstone run ./run-004 -o ./run-004
$ touchstone estimate ./run-004 --by language
$ touchstone grade ./run-004 --score-card card.yaml
$ touchstone bundle ./run-004
./run-004: sealed 8 file(s)
sha256 4c5cf2df7b1ad389d199650325dcde421490caa6c431b4d8819054f0fec0e772

$ touchstone verify ./run-004
./run-004: verified
```

`freeze` pins every image tag to the digest it points at, derives a seed per pack per
replicate, and hashes the result. After that, changing a threshold produces a different
plan hash, so a grade boundary cannot be moved after seeing a result without the artefact
recording that it was.

## Every rate carries its interval

Packs report what happened, one record per item. They never report a rate. The harness
computes every statistic, which is what makes the aggregate re-checkable from a sample
that travels inside the bundle:

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

Booleans become rates with a Wilson interval, continuous scores become means with a seeded
BCa bootstrap interval, and `--by` groups by any stratum key the pack declared.
`estimates.json` names the estimator and its parameters beside every number, so the
arithmetic can be redone in R, in a spreadsheet, or by hand.

No Docker, no database, no network. It is a function of the item records, so the numbers
in a bundle can be recomputed from the bundle years later.

## Verify without Touchstone

The bundle outlives the tool, so nothing in it needs the tool to read. Check any file
against its recorded hash:

```console
$ shasum -a 256 run-004/items.jsonl
69ea741b6e119ebbea72743a32de7636b24cd7975db524b835357466bb8ed667  run-004/items.jsonl
```

Recompute the bundle hash from the manifest alone:

```console
$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
4c5cf2df7b1ad389d199650325dcde421490caa6c431b4d8819054f0fec0e772  -
```

That detects a file edited after sealing. It does not detect a forger who reseals the whole
bundle, which is what external anchoring is for: `freeze --anchor` stamps the plan hash
with OpenTimestamps.

## Containment

A pack that declares no egress runs with no network. A pack that declares an allowlist gets
that allowlist and nothing else: it runs on a Docker network created `--internal`, which
has no route off the host, and a squid sidecar attached to both that network and the
outside is the only way through.

**The proxy never terminates TLS.** It reads the hostname in the `CONNECT` line and the
bytes stay opaque, so it is never trusted with the credentials the pack is using.
Containment does not depend on the pack co-operating either: it is told about the proxy
through `HTTPS_PROXY`, and a pack that ignores that variable is on a network with nowhere
to go.

Every pack also runs under a ceiling it declares in its manifest and `freeze` pins into the
plan: memory, CPUs and processes, with swap pinned to the memory figure. A pack killed for
exceeding its memory is recorded as `out_of_memory` rather than as a timeout.

## The pipeline

```
validate -> freeze -> run -> estimate -> grade -> bundle -> verify
```

| Command | Does | State |
|---|---|---|
| `validate` | check a plan against the manifests of the packs it names | works |
| `freeze` | pin image digests, derive seeds, hash the result | works |
| `run` | execute a frozen plan, write per-item observations | works |
| `estimate` | compute rates and intervals, by stratum | works |
| `grade` | apply a score card, produce DQI indicators | works |
| `bundle` | hash every file in a directory, write `MANIFEST.json` | works |
| `verify` | re-check a bundle against its manifest, offline | works |

**Only `run` needs a container.** Everything after it is a function over files, which is
what lets `verify` run on a plane, in a bank basement, with the wifi off.

## Status

Early, and honest about it. All seven pipeline commands work. The score card format is not
fixed, so `grade` reads a ladder the score card declares rather than one this tool defines.
Version 0.0.1 on PyPI is a placeholder release that predates most of this.

The hashes quoted above are from a real run and are **machine specific**: the lock hash
follows the image digest and the bundle hash follows `environment.json`. They will not
match yours until `example_pack` is published to a registry.

## Requirements

Python 3.12 or later. `freeze` and `run` need the Docker daemon. Nothing else does.

Three runtime dependencies: `pydantic`, `pyyaml`, `typer`. The `offline-install` CI job
builds a wheel, vendors them, installs with `--no-index` and runs it, so the air-gap claim
is tested rather than asserted.

## Contributing

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
uv sync --all-extras --dev
uv run pytest -q
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Commit messages are linted, `main` is
protected, and work lands through a pull request.

## Licence

Apache 2.0.
