# Touchstone

Touchstone seals evaluation output into an evidence bundle: the plan, the per-item
observations, and a SHA-256 over every file. Anyone can re-check that bundle offline,
without this tool and without trusting whoever produced it.

## Status

Early. Three of the seven pipeline commands work and the rest are stubs that exit 2.
Version 0.0.1 is a placeholder release that claims the name.

## Requirements

Python 3.12 or later. `run` will need Docker once it exists; nothing today does.

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
the whole bundle, which is what external anchoring is for. Anchoring is not built yet.

## The pipeline

```
validate -> freeze -> run -> estimate -> grade -> bundle -> verify
```

| Command | Does | State |
|---|---|---|
| `validate` | check a plan against the manifests of the packs it names | works |
| `freeze` | pin image digests, hash the plan, fix seeds and thresholds | exits 2 |
| `run` | execute packs, write per-item observations | exits 2 |
| `estimate` | compute rates and intervals, by stratum | exits 2 |
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
