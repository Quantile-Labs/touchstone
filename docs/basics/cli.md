---
title: CLI reference
description: Every touchstone command, its arguments and its options.
---

# CLI reference

```console
$ touchstone --help
Evaluation runs that produce verifiable evidence.
```

Seven commands, in the order they run. Only `freeze` and `run` need Docker.

```text
validate -> freeze -> run -> estimate -> grade -> bundle -> verify
```

---

## `validate`

Check a plan against the manifests of the packs it names.

```console
$ touchstone validate examples/plan.yaml
examples/plan.yaml: ok, 1 pack(s)
```

```text
touchstone validate [OPTIONS] PLAN_PATH
```

| | |
|---|---|
| `PLAN_PATH` | the plan file. Required. |
| `--manifests`, `-m` | directory holding `<pack_id>/manifest.yaml`. Default `packs`. |
| `--json` | write one machine-readable envelope to stdout instead of prose. See [Machine-readable output](#machine-readable-output). |

Reads each pack's manifest and confirms the plan supplies the systems it requires, that
parameters are the declared types, and that any stratum named exists. Nothing runs.

---

## `freeze`

Pin every image to a digest, materialise seeds, and hash the result.

```console
$ touchstone freeze examples/plan.yaml -o ./run-004
./run-004/plan.lock.json: 1 pack(s) pinned
sha256 81c63db1ae445b9ebc6d4292a4784777884efeee2cbd28be60775e7f0fafbab9
```

```text
touchstone freeze [OPTIONS] PLAN_PATH
```

| | |
|---|---|
| `PLAN_PATH` | the plan file. Required. |
| `--out`, `-o` | where to write the lock and its hash. Default `.`. |
| `--anchor` | timestamp the hash with OpenTimestamps. Needs network. |

**Needs Docker.** See [Freeze and the lock](../running/freeze.md) and
[Anchoring](../bundles/anchoring.md).

---

## `run`

Execute a frozen plan. Refuses one that was never frozen or has been edited.

```text
touchstone run [OPTIONS] LOCK_DIR --out PATH
```

| | |
|---|---|
| `LOCK_DIR` | the directory `freeze` wrote. Required. |
| `--out`, `-o` | where to write the run. **Required.** |
| `--allow-unenforced-egress` | a downgrade. See below. |

**Needs Docker.**

!!! danger "`--allow-unenforced-egress` is a downgrade"

    It runs packs that declared an egress allowlist on the whole network instead. The
    docker backend enforces the allowlist without it, so passing it gives a pack more than
    it declared. `environment.json` records `egress_enforced: false` so a reader knows.
    Use it to develop against a real API. It is not a way to produce evidence for anyone.

See [Running packs](../running/run.md) and [Containment](../running/containment.md).

---

## `estimate`

Compute rates and intervals, by stratum. Offline, no Docker.

```console
$ touchstone estimate run-004 --by rung
run-004/estimates.json: 3 estimate(s) from 6772 item(s)
  evidenced [overall]: 3.6% (95% CI 3.2-4.0%, n=6772)
  evidenced [rung=hybas_entry]: 0.0% (95% CI 0.0-0.1%, n=3682)
  evidenced [rung=real_gauge]: 7.8% (95% CI 6.9-8.8%, n=3090)
```

```text
touchstone estimate [OPTIONS] RUN_DIR
```

| | |
|---|---|
| `RUN_DIR` | the run directory. Required. |
| `--by`, `-b` | stratum key to group by. Repeat for each key on its own **and** crossed. |
| `--calibrate`, `-c` | override the outcome each pack declared its confidence is about. Repeat for more. |
| `--seed` | seed for the bootstrap, so its interval reproduces. Default `0`. |
| `--resamples` | bootstrap resamples for continuous scores. Default `2000`. |
| `--json` | write one machine-readable envelope to stdout instead of prose. See [Machine-readable output](#machine-readable-output). |

Without `--calibrate` the frozen plan decides, and a pack that declared nothing is not
calibrated at all. See [Calibration](../estimation/calibration.md) and [Strata and
rollup](../estimation/strata.md).

---

## `grade`

Apply a score card and produce indicators. Offline, no Docker.

```text
touchstone grade [OPTIONS] RUN_DIR --score-card FILE
```

| | |
|---|---|
| `RUN_DIR` | the run directory. Required. |
| `--score-card`, `-s` | the card to apply: the ladder, its thresholds and its ceilings. **Required.** |
| `--audit`, `-a` | responses for indicators a person assesses rather than the bundle reports. |
| `--prior`, `-p` | the bundle from the evaluation before this one, for indicators that grade movement. |
| `--json` | write one machine-readable envelope to stdout instead of prose. See [Machine-readable output](#machine-readable-output). |

`--audit` responses are copied into the run, so the grade stays recomputable from it.
Without it those indicators are `ungraded`, which is a true statement. Without `--prior`,
movement indicators are `ungraded`, which is what a first evaluation of a system honestly
is.

See [Audit indicators](../scorecards/audit.md) and [Comparing to a prior
bundle](../scorecards/prior.md).

---

## `bundle`

Seal a run into an evidence bundle and hash every file.

```console
$ touchstone bundle ./run-004
./run-004: sealed 9 file(s)
sha256 dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba
```

```text
touchstone bundle [OPTIONS] BUNDLE_DIR
```

| | |
|---|---|
| `BUNDLE_DIR` | the run directory to seal. Required. |

See [Bundle anatomy](../bundles/anatomy.md).

---

## `verify`

Re-check every file in a bundle against its recorded hash. Offline.

```console
$ touchstone verify ./run-004
./run-004: verified
```

```text
touchstone verify [OPTIONS] BUNDLE_DIR
```

| | |
|---|---|
| `BUNDLE_DIR` | the bundle. Required. |
| `--json` | write one machine-readable envelope to stdout instead of prose. See [Machine-readable output](#machine-readable-output). |

Exits non-zero on the first mismatch. See [Verifying a
bundle](../bundles/verifying.md).

---

## `report`

State what a bundle holds against each practice item, as a PDF.

```console
$ touchstone report ./run-004
./run-004.pdf: 10 practice item(s), 3 not met
              met    3.1.3  Every reported figure carries an interval and names the method
          not met    3.2.3  The cost of producing the result is recorded
```

```text
touchstone report [OPTIONS] BUNDLE_DIR
```

| | |
|---|---|
| `BUNDLE_DIR` | the bundle. Required. |
| `--conformance`, `-c` | the practice set to state conformance against. Default `nist-ai-800-2`. |
| `--out`, `-o` | where to write the PDF. Defaults to `<bundle>.pdf` beside the bundle. |
| `--json` | write one machine-readable envelope to stdout instead of prose. See [Machine-readable output](#machine-readable-output). |

Every figure in the document is read from `estimates.json` and `scorecard.json` and none is
recomputed, so the statement and the bundle cannot disagree. The file has no creation date
and no document identifier, so the same bundle produces the same bytes and the statement
can be hashed.

Writing inside the bundle is refused. A file the manifest does not record makes `verify`
report the bundle as tampered with. See [Reporting](../bundles/reporting.md).

---

## Machine-readable output

`validate`, `verify`, `estimate`, `grade` and `report` take `--json`. The command writes one envelope
to stdout, writes nothing else to either stream, and exits with the code it always would.
The prose output is the default and is unchanged.

```console
$ touchstone validate plan.yaml --json
{
  "touchstone_version": "0.4.0",
  "envelope": 1,
  "command": "validate",
  "ok": false,
  "problems": [
    {
      "code": "parameter_unknown",
      "message": "example_pack: pack does not accept parameter 'nope'",
      "severity": "error",
      "path": "plan.yaml",
      "line": 25,
      "column": 7,
      "subject": "example_pack"
    }
  ],
  "result": {"path": "plan.yaml", "packs": 1}
}
```

Branch on `code`. It is stable, and `message` is the sentence the human output prints,
which gets rewritten whenever it reads badly. `line` and `column` are 1-indexed and are
absent rather than zero where a check cannot say where it is looking, which is every
failure `verify` reports: a hash is a fact about a whole file.

`severity` is `error` or `warning`. A warning is a finding the command succeeded past, so
an indeterminate grade arrives as one and `ok` stays true. Treating the two the same fails
runs that measured exactly what they set out to measure.

`result` is what the command produced. For `estimate` and `grade` that is where the numbers
were written rather than the numbers themselves, because `estimates.json` and
`scorecard.json` are contracts of their own and a second copy here would be a second shape
to keep in step.

The schema is [`envelope.schema.json`](../schemas/envelope.schema.json), and the model
behind it is `contracts/diagnostics.py`. `envelope` is the version of the shape: it goes up
when a field is removed or changes meaning, and not when one is added, so a reader that
ignores what it does not recognise keeps working.

---

## `version`

```console
$ touchstone version
touchstone 0.4.0
```
