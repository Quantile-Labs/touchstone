# Touchstone

Touchstone is an AI evaluation harness that produces results you can check yourself. It
runs your tests against an AI system inside containers, works out every number itself, and
seals the whole run into one folder holding the plan, one row per test item, and a SHA-256
of every file. The system under test can be an LLM, an LLM application, a classifier or a
scoring model, and the harness treats them all the same way.

Anyone can re-check that folder offline with `shasum`, which means you do not have to
trust whoever ran it. Most evaluation tools hand you a score and ask you to believe it,
whereas this one hands you the working alongside the answer.

- **Every number carries an interval**: 47 of 50 and 940 of 1000 are both 94%, and only
  one of them backs a claim about a 90% bar. A bare percentage is not representable here.
- **Grades can say "I don't know"**: when the interval crosses a grade boundary, the answer
  is `indeterminate` and names the two grades it sits between, instead of rounding up.
- **Packs report facts, not scores**: a pack writes one row per item saying what happened.
  Touchstone computes every rate. The rows ship inside the bundle, so anyone can redo it.
- **Checkable without this tool**: `shasum -a 256 -c PLAN.sha256` verifies a run with
  nothing of ours installed. Three dependencies, and it works with the wifi off.
- **Contained**: a pack reaches the hosts it declared and nothing else, on a network with
  no route out. The proxy never decrypts traffic, so it never sees your API keys.

## The 94% problem

Two AI systems are tested. Both get 94%. One was tested on 50 items, the other on 1,000:

```
47 of 50     ->  94%
940 of 1000  ->  94%
```

Every evaluation tool reports those two the same way, even though only one of them backs a
claim about a 90% bar. Touchstone prints the interval next to the rate so you can tell
them apart:

```
94.0%  (95% CI 83.5-98.8%, n=50)     <- cannot back the claim
94.0%  (95% CI 92.4-95.4%, n=1000)   <- can
```

A pass-or-fail test over 50 items is a percentage, and percentages have error bars, which
is the first thing anyone learns about them. Most AI evaluation scores things pass or fail
and then reports the percentage with no error bar at all, which is an odd place for the
field to have ended up.

Grades work the same way. A score card gives a grade when a number clears a threshold. If
the error bar crosses that threshold, the honest answer is not the better grade:

```console
headline_accuracy: indeterminate, A or C  [0.91, 0.8783 to 0.9345, n=400]
    the interval spans the A boundary of 0.9, so the grade is A or C and the evidence does not say which
worst_stratum: indeterminate, A or B  [0.861, 0.803 to 0.905, n=180, language=pcm]
```

Grading the middle number on its own would have printed two confident letters, neither of
which the evidence supports, so `indeterminate` is the answer that tells you to go and get
more data.

**A few things Touchstone is not.** It is not a benchmark or a leaderboard, because it
scores one system doing one job for one population rather than ranking models against each
other. It is not a safety or capability test, and it is not a certificate: a grade says
what the evidence supports, and nothing in it amounts to an approval.

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

`freeze` locks each container image to an exact version, fixes the random seeds, and
hashes the whole plan. After that, changing a pass mark changes the hash. So nobody can
move a grade boundary after seeing the result without it showing.

## Who does the maths

**Whoever works out the score is who you end up trusting.** If the test container hands
you "94% accuracy" then you are trusting whoever wrote that container, and often that is
the same people who would like the number to look good.

So packs here do not work out scores at all. A pack writes one row per item saying what
happened, Touchstone does the arithmetic, and the rows travel inside the bundle so that
anyone can redo the sums:

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

True or false answers become rates with a Wilson interval. Scores become averages with a
bootstrap interval, seeded so it comes out the same next time. `--by` splits the numbers
by any group the pack declared: language, region, difficulty, whatever it tracks.

`estimates.json` writes the method and its settings next to every number, so you can redo
the sums in R, in a spreadsheet, or on paper.

This step needs no Docker, no database and no network. It reads the rows and nothing else,
so the numbers in a bundle can be worked out again years later.

## Verify without Touchstone

A bundle should still make sense after this tool is gone, so nothing in it needs this
tool to read. Check any file against its recorded hash:

```console
$ shasum -a 256 run-004/items.jsonl
69ea741b6e119ebbea72743a32de7636b24cd7975db524b835357466bb8ed667  run-004/items.jsonl
```

Work out the whole bundle's hash from the manifest:

```console
$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
4c5cf2df7b1ad389d199650325dcde421490caa6c431b4d8819054f0fec0e772  -
```

That catches a file changed after the bundle was sealed. It does not catch someone who
re-seals the whole thing, because they could redo the hashes too. For that you need a
timestamp from outside: `freeze --anchor` stamps the plan hash with OpenTimestamps, which
proves the plan existed before the run.

## Containment

A pack that asks for no network gets none. A pack that lists the hosts it needs gets those
hosts and nothing else. It runs on a Docker network with no route out, and a small proxy
is the only door.

**The proxy never decrypts anything.** It reads the hostname the pack asks for and passes
the rest through untouched, so it never sees your API keys.

**A badly behaved pack cannot get around it.** Touchstone tells the pack where the proxy
is, but that is only politeness. The pack is on a network with nowhere else to go, so
ignoring the proxy gets it nothing.

Each pack also says how much memory, CPU and how many processes it needs, and `freeze`
writes those limits into the plan. Swap is capped too, or a pack given 2 GB could quietly
use 4. A pack killed for using too much memory is recorded as `out_of_memory`, not as a
timeout, because those are different problems.

## The pipeline

```
validate -> freeze -> run -> estimate -> grade -> bundle -> verify
```

| Command | Does | State |
|---|---|---|
| `validate` | check the plan against what each pack says it needs | works |
| `freeze` | lock the image versions, fix the random seeds, hash the plan | works |
| `run` | run the packs, write one row per test item | works |
| `estimate` | work out the rates and their intervals, split by group | works |
| `grade` | apply a score card and give each indicator a grade | works |
| `bundle` | hash every file and write `MANIFEST.json` | works |
| `verify` | re-check a bundle against its manifest, offline | works |

**Only `run` needs a container.** Everything after it just reads files, so `verify` works
on a plane, in a bank basement, with the wifi off.

## Status

Early, and saying so. All seven commands work. The score card format is not settled yet,
so `grade` uses whatever grade ladder the score card gives it rather than one built in.
Version 0.0.1 on PyPI is a placeholder and is older than most of this.

The hashes above come from a real run, but they are **specific to that machine**. They
will not match yours until `example_pack` is published somewhere you can pull it from.

## Requirements

Python 3.12 or later. `freeze` and `run` need Docker running. Nothing else does.

Three dependencies: `pydantic`, `pyyaml`, `typer`. CI builds the package, downloads those
three, installs everything with the network switched off and runs it. The offline claim is
tested on every change, not just written down.

## Contributing

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
uv sync --all-extras --dev
uv run pytest -q
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Commit messages are checked by a linter,
`main` is protected, and changes go in through a pull request.

## Licence

Apache 2.0.
