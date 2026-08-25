# Touchstone

Touchstone seals evaluation output into an evidence bundle: the plan, the per-item
observations, and a SHA-256 over every file. Anyone can re-check that bundle offline,
without this tool and without trusting whoever produced it.

## Status

Early. Six of the seven pipeline commands work and `grade` is a stub that exits 2.
Version 0.0.1 on PyPI is a placeholder release that predates most of this.

## Requirements

Python 3.12 or later. `freeze` and `run` need the Docker daemon. Nothing else does:
`estimate`, `bundle` and `verify` are functions over files.

## Install

```bash
pip install touchstone-dqi
```

The command is `touchstone`. To work on it instead:

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Check a plan

A plan names the packs to run and the systems to run them against. `validate` reads it
against each pack's `manifest.yaml` and reports what does not line up:

```console
$ touchstone validate plan.yaml
plan.yaml: ok, 1 pack(s)

$ touchstone validate broken.yaml
broken.yaml: 1 problem(s)
  example_pack: pack does not accept parameter 'max_itemz'
```

It resolves packs from `./packs`. Pass `--manifests` to point somewhere else. No
container runs, and it exits 1 if anything is wrong.

## Freeze a plan before running it

`freeze` resolves every image tag to the digest it points at, derives a seed for each pack
and replicate from the plan's root seed, and hashes the result:

```console
$ touchstone freeze plan.yaml -o ./run-004
./run-004/plan.lock.json: 1 pack(s) pinned
sha256 2005a468dbe221c062965302d052b5c3c4253c4266c9c66b3c5011bc4bbf2e6b
check it with: shasum -a 256 -c run-004/PLAN.sha256
```

The lock is canonical JSON and `PLAN.sha256` is in shasum's own format, so anyone can
check it without installing anything:

```console
$ shasum -a 256 -c PLAN.sha256
plan.lock.json: OK
```

Add `--anchor` to timestamp the hash with OpenTimestamps. That step needs the network and
the `ots` client, so it is opt-in; everything else in `freeze` works offline. The receipt
lands in `anchors/` next to a copy of the file it covers, with a note saying what it does
and does not yet prove.

`run` executes a frozen plan and refuses one that was never frozen or has been edited
since. Not a warning, a non-zero exit:

```console
$ touchstone run ./run-004 -o ./bundle
./bundle: ok

$ touchstone run ./edited -o ./bundle
plan.lock.json has changed since it was frozen.
  frozen:  2005a468dbe221c062965302d052b5c3c4253c4266c9c66b3c5011bc4bbf2e6b
  on disk: f55de7788a0d2b2cfcc69029f62dbfa9d5955f61415136050c095b1f6e1fd29b
```

Every run writes `ledger/RUNLOG.jsonl` as it goes, opening with the plan hash it ran
against. The tool writes it, not a person, and not afterwards. It also writes
`environment.json`: the backend, the digests that actually ran, and whether each pack was
held to the network it declared.

A pack that declares no egress runs with no network. A pack that declares an allowlist is
refused, because Docker cannot enforce one without a proxy that does not exist yet.
`--allow-unenforced-egress` runs it with the whole network and records that it did.

## Estimate

`estimate` reads the per-item observations and computes the statistics itself. Packs
report what happened; they never report a rate. Every number comes back with an interval
and a denominator, and a bare proportion is not representable:

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

Booleans become rates with a Wilson interval, continuous scores become means with a BCa
bootstrap interval, and `--by` groups by any stratum key the pack declared. `estimates.json`
names the estimator and its parameters beside every number, so the arithmetic can be redone
in R, in a spreadsheet, or by hand without this tool.

Nothing here needs Docker, a database or a network. It is a function of the item records,
which means the numbers in a bundle can be recomputed from the bundle years later.

## Seal and verify a bundle

`bundle` hashes every file under a directory and writes `MANIFEST.json`:

```console
$ touchstone bundle run-004
run-004: sealed 3 file(s)
sha256 f57c02f1af4a277d404c29af41cb8953a513a1b0ca38884fcacaf0cbf3359d19
```

The printed hash covers the file list, so identical content seals to the same value on
any machine. Sealing a directory that already has a manifest is an error.

`verify` re-checks the bundle and names what moved:

```console
$ touchstone verify run-004
run-004: verified

$ touchstone verify tampered
tampered: 1 failure(s)
  hash mismatch: items.jsonl
```

Exit 0 means every file matches its recorded hash and no unrecorded file is present.
Exit 1 means it does not. There is no network call, no database and no config file.

## Verify without Touchstone

The bundle outlives the tool, so nothing in it needs the tool to read. Check any single
file against its recorded hash:

```console
$ shasum -a 256 run-004/items.jsonl
63a6e0f7ba35198b686265cab8c8b389599c8bb6c3fcff06234d5b68cda0d82f  run-004/items.jsonl
```

Recompute the bundle hash from the manifest alone:

```console
$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
f57c02f1af4a277d404c29af41cb8953a513a1b0ca38884fcacaf0cbf3359d19  -
```

That hash detects a file edited after sealing. It does not detect a forger who reseals
the whole bundle, which is what external anchoring is for. `freeze --anchor` stamps the
plan hash with OpenTimestamps; see `anchors/README.md` in a stamped run for what a fresh
receipt does and does not yet prove.

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
| `grade` | apply a score card, produce DQI indicators | exits 2 |
| `bundle` | hash every file in a directory, write `MANIFEST.json` | works |
| `verify` | re-check a bundle against its manifest, offline | works |

Only `run` needs a container. Everything after it is a function over files.

## Design

Three choices shape the rest:

- Packs emit one observation per item, not a summary. Touchstone computes the rates and
  intervals, so a reader can recompute them from the sample in the bundle.
- Runs are pinned before they start. `freeze` resolves image tags to digests and hashes
  the plan; `run` refuses a plan that has changed since.
- A missing file, an unresolvable digest or a stale hash is an error with a non-zero
  exit, never a warning.

To write a pack, see [docs/packs.md](docs/packs.md).

## Licence

Apache 2.0. See [LICENSE](LICENSE).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. The commit message and code style rules
are enforced by CI.

Maintained by [Quantile Labs](https://quantilelabs.com).
