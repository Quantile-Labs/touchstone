<h1 align="center">Touchstone</h1>

<p align="center"><strong>AI evaluation results that anyone can check.</strong></p>

<p align="center">
  <a href="https://touchstone.quantilelabs.com">Documentation</a> ·
  <a href="https://pypi.org/project/touchstone-dqi/">PyPI</a> ·
  <a href="#getting-started">Getting started</a>
</p>

Touchstone runs an evaluation in a container, computes the results itself, and seals
everything into one folder. Hand that folder to anyone. They can verify every number in
it, with or without Touchstone.

```bash
pip install touchstone-dqi
```

## Every number comes with its range

Two systems score 94%. One was tested on 50 items, the other on 1,000.

```
94.0%  (95% CI 83.8-97.9%, n=50)     <- cannot back a claim about a 90% bar
94.0%  (95% CI 92.4-95.3%, n=1000)   <- can
```

Touchstone never prints a rate without its interval and its denominator.

## It says when it does not know

When the range crosses a grade threshold, the grade is reported as inconclusive.

```console
Correct answers over the whole sample (headline_accuracy)
  Grade: B or C, inconclusive
  Score: 0.72, likely range 0.6741 to 0.7617, 400 results
  Reason: The likely range crosses the B threshold (0.7), so the grade is B or C
```

## Touchstone does the maths

A pack reports one row per test item and no scores. Touchstone computes every rate from
those rows, and the rows stay in the bundle, so the arithmetic can be redone in R, in a
spreadsheet or on paper.

This is a real run from published work. A flood warning system was asked, for each of
6,772 river locations, whether it could show evidence of coverage.

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
  not quantified: marking, item selection, item leakage, endpoint identity
  assumptions not checked: unidimensional, functional form, independent items
```

True and false answers become rates with a Wilson interval. Scores become means with a
seeded bootstrap. `--by` splits by any group the pack declared. Each figure is stored with
its method and settings. `tests/test_estimate_credential.py` reproduces the numbers above
from the item records.

## One folder holds everything

A bundle is plain files: JSON, JSON Lines and hashes. No database and no proprietary
format. The run below is 204 KB.

```
run-004/
├── MANIFEST.json        every file below, with its SHA-256 and size
├── PLAN.sha256          the plan hash, checkable with shasum alone
├── plan.lock.json       image digests, seeds, declared egress, resource ceilings
├── environment.json     what it ran on, what it cost, whether egress was enforced
├── items.jsonl          one row per test item, stamped with the pack that produced it
├── estimates.json       every rate with its interval, method, parameters, denominator
├── scorecard.json       the grade each indicator got, and what decided it
├── ledger/RUNLOG.jsonl  append-only, written as each event happened
└── runs/                the per-unit item files, before merging
```

## Anyone can verify it

One offline command checks every file against the manifest.

```console
$ touchstone verify ./run-004
./run-004: verified
```

The same check works with standard tools and no Touchstone at all.

```console
$ shasum -a 256 run-004/items.jsonl
fc127dc53abc97b4528d666a732707ca5b010dd108713ad830e540e0d3d932b0  run-004/items.jsonl

$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba  -
```

This catches a file changed after sealing. It does not catch someone who seals the whole
folder again with new hashes. For that, `freeze --anchor` stamps the plan hash with
OpenTimestamps, which proves the plan existed before the run.

## Evaluations stay contained

A pack that asks for no network gets none. A pack that lists hosts reaches those hosts and
nothing else. It runs on a Docker network with no route out, and a small proxy is the only
way through. The proxy reads the hostname and passes the rest through untouched, so it
never sees your API keys.

Each pack declares memory, CPU and process limits, and `freeze` writes them into the plan.
Swap is capped too. A pack killed for memory is recorded as `out_of_memory`.

## Getting started

Python 3.12 or later. `freeze` and `run` need Docker. Nothing else does.

The examples use `examples/plan.yaml` and `packs/example_pack` from the source repository,
which the package does not include.

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
docker build -t example_pack:1.0 packs/example_pack
```

### Write a plan

A plan says what to run against what. This is `examples/plan.yaml`, whole.

```yaml
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

`access_tier` caps what any grade may later claim. `replicates: 2` runs everything twice,
so run-to-run instability is measured.

### Run it

```console
$ touchstone validate examples/plan.yaml
examples/plan.yaml: ok, 1 pack(s)

$ touchstone freeze examples/plan.yaml -o ./run-004
./run-004/plan.lock.json: 1 pack(s) pinned
sha256 81c63db1ae445b9ebc6d4292a4784777884efeee2cbd28be60775e7f0fafbab9

$ touchstone run ./run-004 -o ./run-004
$ touchstone estimate ./run-004 --by language
$ touchstone grade ./run-004 --score-card examples/scorecard.yaml
$ touchstone bundle ./run-004
./run-004: sealed 9 file(s)
sha256 dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba
```

`freeze` pins each image to a digest, fixes the seeds and hashes the plan. A grade
boundary moved after seeing the result would show.

> **Note.** These hashes came from a real run on one machine. `example_pack` is not yet
> published to a registry, so the image digest and every hash after it will differ on
> yours. The commands themselves run.

### Grade it

A score card is the rubric, written as data. This is one indicator from
`examples/scorecard.yaml`.

```yaml
levels: ["A", "B", "C", "unfit"]

tier_ceilings:
  black_box: "B"

indicators:
  - id: headline_accuracy
    metric:
      source: estimate
      name: correct
      pack_id: example_pack
    assessment:
      - level: "A"
        condition: greater_equal_ci_lower
        threshold: 0.9
      - level: "B"
        condition: greater_equal_ci_lower
        threshold: 0.7
```

`greater_equal_ci_lower` reads the bottom of the interval, so a wide interval cannot earn
a level the sample does not support. The levels and thresholds in the example file are
invented to show the shape.

## The pipeline

```
validate -> freeze -> run -> estimate -> grade -> bundle -> verify
```

| Command | Does | Needs |
|---|---|---|
| `validate` | check the plan against what each pack declares it needs | the plan and the packs |
| `freeze` | lock image versions, fix seeds, hash the plan | Docker |
| `run` | run the packs, write one row per test item | Docker |
| `estimate` | compute rates and intervals, split by group | the bundle |
| `grade` | apply a score card, grade each indicator | the bundle and a card |
| `bundle` | hash every file, write `MANIFEST.json` | the run directory |
| `verify` | re-check a bundle against its manifest, offline | the bundle |
| `report` | state what a bundle holds against NIST AI 800-2, as a PDF | the bundle |

Everything after `run` reads files. `verify` works on a plane with the wifi off.

## Who it is for

People who have to trust a result before making a decision: auditors, procurement teams,
risk teams, regulators, and whoever produces evidence for them.

For rapid prompt experimentation, use Inspect. When you have a result you are ready to
stand behind and publish, use Touchstone.

## What it does not prove

**The interval is sampling error only.** It is how far the number would move if you drew
another set of items the same way. Three larger errors sit outside it. Your items may not
be a random sample of deployment. Whatever decided `correct` has its own error rate. A
leaked item set measures recall. Two other sources are measured and reported beside the
rate: variance between replicates, and calibration error against the system's own stated
confidence.

**Nothing stops someone running it ten times and sealing the run they liked.** Run
selection leaves no trace in any file the tool produces. Closing that gap takes a
commitment, made in advance, to publish every run against a plan.

**A pinned image is not a pinned system.** `freeze` pins the code that does the asking.
The system being asked is often a hosted API, and it can change under the same model name
between two runs of the same frozen plan.

**A grade is not an approval.** Touchstone is not a benchmark, a leaderboard, a safety
test or a certificate. A grade says what the evidence supports.

## Status

Early. 0.8.0 is the current release. All eight commands work and are tested, and this
document describes the code on PyPI.

The four files a person writes have published [JSON
Schemas](https://touchstone.quantilelabs.com/reference/schemas/), so an editor with a YAML
language server checks a plan as it is typed. `validate`, `verify`, `estimate`, `grade`
and `report` take `--json`.

The score card format is not settled. `grade` applies whatever ladder the card gives it,
and `examples/scorecard.yaml` shows the shape, not a rubric to adopt.

The package is `touchstone-dqi` because `touchstone` was taken on PyPI. DQI is the
deployment quality index this is being built to carry. It is separate, unpublished work,
and nothing here grades against it.

## Contributing

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
uv sync --all-extras --dev
uv run pytest -q
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Commit messages are linted, `main` is
protected, changes go in through a pull request, and every commit is signed off under the
[Developer Certificate of Origin](https://developercertificate.org/). To write a pack, see
[Writing a pack](https://touchstone.quantilelabs.com/extending/writing-a-pack/).

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) applies to every space this project uses, and
[GOVERNANCE.md](GOVERNANCE.md) says who decides.

## Security

Report a vulnerability privately through the [Security
tab](https://github.com/Quantile-Labs/touchstone/security), not in a public issue.
[SECURITY.md](SECURITY.md) lists what is in scope and the two known gaps.

## Licence

Apache 2.0. Copyright is held by Quantile Labs, and every source file carries an SPDX
header. There is no contributor licence agreement, so contributed code cannot be
relicensed without its authors.

Three runtime dependencies: `pydantic`, `pyyaml`, `typer`. CI installs the package with
the network switched off and runs it, so the offline claim is tested on every change.
