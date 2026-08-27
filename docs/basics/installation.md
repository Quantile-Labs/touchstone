---
title: Installation
description: Installing touchstone-dqi, and which of the seven commands need Docker.
---

# Installation

```bash
pip install touchstone-dqi
```

Python 3.12 or later.

The distribution is named `touchstone-dqi` because `touchstone` was already taken on PyPI.
The command it installs, the package you import, and the name of the project are all
`touchstone`:

```console
$ touchstone version
touchstone 0.2.1
```

## What needs Docker

Two of the seven commands. Everything else reads and writes files.

| Command | Docker |
|---|---|
| `validate` | no |
| `freeze` | **yes**, it resolves each image to a digest |
| `run` | **yes**, it runs the packs |
| `estimate` | no |
| `grade` | no |
| `bundle` | no |
| `verify` | no |

This is deliberate. Whoever is handed a bundle has to be able to check it, and requiring
them to install a container runtime to do arithmetic on a JSON Lines file would put the
check out of reach of most of the people who need it. `verify` works on a plane with the
wifi off.

## Dependencies

Three, at runtime: `pydantic`, `pyyaml`, `typer`.

The offline claim is tested rather than asserted. CI installs the package with the network
switched off and runs it on every change.

## From source

```bash
git clone https://github.com/Quantile-Labs/touchstone
cd touchstone
uv sync --all-extras --dev
uv run pytest -q
```

See [Contributing](../project/contributing.md) for what the hooks and the commit lint
expect.

## Docker, for `freeze` and `run`

Any Docker daemon the CLI can reach. There is nothing to configure: the backend talks to
whatever `docker` on your `PATH` talks to.

!!! note "The container runs as you"

    Packs run as the user who invoked Touchstone, not as root and not as the image's
    `USER`. A bind mount on Linux keeps host ownership, so a pack running as anyone else
    could not write its results. See [Writing a pack](../extending/writing-a-pack.md).
