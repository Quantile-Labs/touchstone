# Touchstone

**An open-source harness for AI evaluations that seal into a checkable evidence bundle.**

Touchstone runs an evaluation in containers, works out every number itself rather than
taking the system's word for any of them, and writes the plan, one row per test item and a
SHA-256 of every file into a folder anyone can re-check with `shasum`. Core features:

- **Bundles checkable without this tool.** Every file is JSON, JSON lines or a hash. No
  database, no index, no proprietary format.
- **Every rate carries an interval.** A bare percentage cannot be represented at all.
- **Grades can say `indeterminate`** when the interval crosses a threshold, instead of
  printing a letter the evidence does not support.
- **Packs report facts, never scores.** The arithmetic is Touchstone's, and the rows
  travel in the bundle so anyone can redo it.
- **Containment.** A pack reaches the hosts it declared and nothing else; the proxy that
  lets it out never decrypts anything.
- **A score card is data.** Levels, thresholds and access-tier ceilings are read from a
  YAML file, so a card with three levels and a card with eight both work.

It is built for people handed a result who have to decide whether to act on it. Auditors,
procurement, risk, regulators, and the teams producing evidence for them. It is not
built for iterating on a prompt: freezing plans and sealing bundles are overhead in a loop
where you change a line and rerun twenty times. Use Inspect while exploring, and this for
the claim you publish.

## Getting started

```bash
pip install touchstone-dqi
```

Python 3.12 or later. `freeze` and `run` need Docker; nothing else does.

> **Note.** The hashes below came from a real run and are specific to the machine that
> made them. `example_pack` is not published to a registry yet, so the image digest, and
> every hash that follows it, will differ on yours until it is. The commands themselves
> run.

## The 94% problem

Two systems are tested. Both get 94%. One was tested on 50 items, the other on 1,000:

```
94.0%  (95% CI 83.5-98.8%, n=50)     <- cannot back a claim about a 90% bar
94.0%  (95% CI 92.4-95.4%, n=1000)   <- can
```

Grades work the same way. If the error bar crosses the threshold, the honest answer is not
the better letter:

```console
headline_accuracy: indeterminate, A or C  [0.91, 0.8783 to 0.9345, n=400]
    the interval spans the A boundary of 0.9, so the evidence does not say which
```

**The interval is sampling error, and only that.** It is how far the number would move if
you drew another set of items the same way. Three larger errors are not in it: your items are
not a random sample of deployment, whatever decided `correct` has its own error rate
(correlated, not independent, when the judge is a model), and a leaked item set measures
recall rather than ability. Two of the usual suspects *are* measured and reported next to
the rate: between-replicate variance, which shows both how far the rate moved and how many
individual items flipped, and calibration error against the system's own stated confidence.

It is precision. It is not accuracy. See [what this does not
prove](#what-this-does-not-prove) for the limits a hash cannot fix.

## Producing a bundle

A plan says what to run against what. This is `examples/plan.yaml`, whole:

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

`access_tier` caps what any grade may later claim. `replicates: 2` runs the whole thing
twice, which makes run-to-run instability measurable rather than assumed.

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

`freeze` locks each image to a digest, fixes the seeds and hashes the plan, so a grade
boundary cannot be moved after seeing the result without it showing.

## Checking a bundle you were handed

A bundle is a folder, 204 KB for the run above, and it should still make sense after
Touchstone is gone:

```
run-004/
├── MANIFEST.json        every file below, with its SHA-256 and size
├── PLAN.sha256          the plan hash, checkable with shasum alone
├── plan.lock.json       image digests, seeds, declared egress, resource ceilings
├── environment.json     what it ran on, and whether egress was enforced
├── items.jsonl          one row per test item, stamped with the pack that produced it
├── estimates.json       every rate with its interval, method, parameters, denominator
├── scorecard.json       the grade each indicator got, and what decided it
├── ledger/RUNLOG.jsonl  append-only, written as each event happened
└── runs/                the per-unit item files, before merging
```

Check any file against its recorded hash, or recompute the bundle hash from the manifest:

```console
$ shasum -a 256 run-004/items.jsonl
fc127dc53abc97b4528d666a732707ca5b010dd108713ad830e540e0d3d932b0  run-004/items.jsonl

$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba  -
```

That catches a file changed after sealing, not someone who re-seals the whole thing and
redoes the hashes. For that you need a timestamp from outside: `freeze --anchor` stamps
the plan hash with OpenTimestamps, proving the plan existed before the run.

If you would rather install it than drive `shasum` by hand, one offline command walks
every file in the manifest and exits non-zero on the first mismatch:

```console
$ touchstone verify ./run-004
./run-004: verified
```

## Who does the maths

Whoever computes the score is who you end up trusting. If the container hands you "94%
accuracy", you are trusting whoever wrote that container, and often that is the people who
would like the number to look good. So packs here emit one row per item and no scores at all.

A real run, from published work: a flood warning system asked, for each of 6,772 river
locations, whether it could show evidence of coverage. `tests/test_estimate_credential.py`
reproduces these numbers from the item records, to the last bit of both bounds.

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

True/false answers become rates with a Wilson interval; scores become averages with a
seeded bootstrap. `--by` splits by any group the pack declared. `estimates.json` records
the method and its settings next to every number, so the sums can be redone in R, in a
spreadsheet or on paper. This step needs no Docker, no database and no network.

## Score cards

A score card is the rubric, as data. One indicator from `examples/scorecard.yaml`:

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

`greater_equal_ci_lower` reads the **bottom** of the interval, so a wide interval cannot
buy a level the sample does not support. The levels and thresholds in the example file are
invented to show the shape, not to mean anything.

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

Only `run` needs a container. Everything after it reads files, so `verify` works on a
plane with the wifi off.

## Containment

A pack that asks for no network gets none; a pack that lists hosts gets those and nothing
else. It runs on a Docker network with no route out, and a small proxy is the only door.
The proxy reads the hostname and passes the rest through untouched, so it never sees your
API keys. A pack that ignores it gets nowhere, because there is nowhere else to go.

Each pack declares memory, CPU and process limits, which `freeze` writes into the plan.
Swap is capped too. A pack killed for memory is recorded as `out_of_memory`, not as a
timeout.

## What this does not prove

**Nothing stops someone running it ten times and sealing the run they liked.** Run
selection leaves no trace in any artefact the tool produces. Closing it takes a commitment
made in advance to publish every run against a plan, which is a process somebody keeps and
not something `shasum` checks.

**A pinned image is not a pinned system.** `freeze` pins the code that does the asking.
The system being asked is often a hosted API, and there is no digest for somebody else's
endpoint: it can change under the same model name between two runs of the same frozen
plan. Fixed seeds make the harness deterministic, not the system under test.

And Touchstone is not a benchmark, a leaderboard, a safety test or a certificate. A grade
says what the evidence supports; nothing in it amounts to an approval.

## Status

Early, and saying so. 0.2.1 is the current release, all seven commands work and are
tested doing it, and this document describes the code that is on PyPI. What is not settled is the
score card format, so `grade` applies whatever ladder the card gives it rather than one
built in, and `examples/scorecard.yaml` shows the shape rather than a rubric anyone should
adopt. The package is `touchstone-dqi` because `touchstone` was taken on PyPI. DQI is the
deployment quality index this is being built to carry, which is separate work and is not
published, so nothing here grades against it.

## Contributing

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
uv sync --all-extras --dev
uv run pytest -q
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Commit messages are linted, `main` is
protected, and changes go in through a pull request. See [Writing a
pack](https://touchstone.quantilelabs.com/extending/writing-a-pack/) to write a pack.

## Licence

Apache 2.0. Three runtime dependencies: `pydantic`, `pyyaml`, `typer`. CI installs the
package with the network switched off and runs it, so the offline claim is tested on every
change.
