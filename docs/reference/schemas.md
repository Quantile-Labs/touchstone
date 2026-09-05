---
title: Editor schemas
description: >-
  JSON Schemas for the four files a person writes by hand, generated from the
  pydantic contracts and published for any editor with a YAML language server.
---

# Editor schemas

Four files in a Touchstone project are written by a person: a plan, a score card, a pack
manifest, and the audit responses an assessor fills in. Each has a JSON Schema, generated
from the same pydantic model `touchstone validate` uses, so an editor can complete keys,
show what each one means, and flag a mistake before the command is run.
{ .lede }

| File | Schema | Model |
|---|---|---|
| `plan.yaml` | [`plan.schema.json`](../schemas/plan.schema.json) | `contracts.plan.Plan` |
| `scorecard.yaml` | [`scorecard.schema.json`](../schemas/scorecard.schema.json) | `contracts.scorecard.ScoreCard` |
| `manifest.yaml` | [`pack-manifest.schema.json`](../schemas/pack-manifest.schema.json) | `contracts.manifest.Manifest` |
| `audit.yaml` | [`audit.schema.json`](../schemas/audit.schema.json) | `contracts.audit.AuditResponses` |

One more is published for a file nobody writes. `--json` output has
[`envelope.schema.json`](../schemas/envelope.schema.json), generated the same way, because
the reader who most needs a schema is the one parsing output they did not author. See
[Machine-readable output](../basics/cli.md#machine-readable-output).

The pack manifest is named `pack-manifest` because a bundle also holds a `MANIFEST.json`,
and the two describe different things.

## Wiring one up

Put the schema on the first line of the file. One comment, and every editor with a YAML
language server picks it up, with no per-editor configuration and nothing to install:

```yaml
# yaml-language-server: $schema=https://touchstone.quantilelabs.com/schemas/plan.schema.json
plan_name: "demo"
access_tier: "black_box"
```

`examples/plan.yaml`, `examples/scorecard.yaml` and `packs/example_pack/manifest.yaml` all
carry theirs, so a file copied out of this repository as a starting point arrives wired.

This works in VS Code with the [YAML
extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml), in
JetBrains IDEs, in Neovim through `yaml-language-server`, and in anything else that speaks
the same protocol. There is no Touchstone editor extension to install, and the schema is
the reason there does not need to be one.

## Wiring a whole directory

Where you would rather not touch the files, map them by glob instead. In VS Code, in
`.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "https://touchstone.quantilelabs.com/schemas/plan.schema.json": ["plans/*.yaml"],
    "https://touchstone.quantilelabs.com/schemas/scorecard.schema.json": ["cards/*.yaml"],
    "https://touchstone.quantilelabs.com/schemas/pack-manifest.schema.json": [
      "packs/*/manifest.yaml"
    ]
  }
}
```

The globs are yours to pick. `plan.yaml` is too common a filename to claim globally, which
is why these are not registered with SchemaStore and why the modeline is the recommended
route.

## What a schema catches, and what it does not

It reads the shape of a file: an unknown key anywhere in it, a string where a number
belongs, a missing required field, a `replicates` of zero, a pack id with a capital letter
in it.

Three checks stay with `touchstone validate`, because no schema can see them:

* whether a pack the plan names has a manifest at all,
* whether the systems and parameters the plan passes are the ones that pack declares,
* whether every level a score card rule awards appears in its own `levels`.

Every object in every schema is closed, at each level of nesting, because every contract
sets `extra="forbid"`. A misspelled key inside a `packs` entry is caught in the editor and
by `touchstone validate`, and the two agree because the schema is generated from the model
the command runs.

The exception is `params`, on a pack and on a system, which is free-form by design: the
keys are the pack's, and only the pack's manifest knows them. Nothing completes there, and
`touchstone validate` is what checks a parameter against the pack that has to accept it.

## Versions

The published schemas track the latest release. To pin them to the version you have
installed, generate them from it:

```bash
git clone https://github.com/Quantile-Labs/touchstone
uv run python scripts/gen_schemas.py
```

That writes `docs/schemas/` from the contracts in the working tree. The test suite runs
the same script with `--check`, so a contract that changes without its schema fails CI and
the published files cannot drift away from the code they describe.
