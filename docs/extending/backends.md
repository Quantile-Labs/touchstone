---
title: Backend protocol
description: >-
  The seven-method contract every runtime implements, and why `isolation` is the
  field that makes an honest backend possible.
---

# Backend protocol

`ContainerBackend` is the contract every runtime implements, so the harness cannot tell
them apart.
{ .lede }

```python
@runtime_checkable
class ContainerBackend(Protocol):
    name: str
    isolation: str

    def run(self, spec: RunSpec) -> RunResult: ...
    def shutdown(self, run_ids: list[str]) -> None: ...
    def check_images(self, images: list[str]) -> dict[str, bool]: ...
    def pull_images(self, images: list[str]) -> None: ...
    def resolve_digest(self, image: str) -> str: ...
    def extract_manifest(
        self, image: str, manifest_path: str = MANIFEST_PATH
    ) -> Manifest | None: ...
```

One backend ships: `docker`.

## `isolation` is the load-bearing field

> One word for how well this backend contains a pack, recorded in every bundle it
> produces. **A subprocess runner is honest here or it is worse than useless.**

It goes into `environment.json` and travels with the evidence. A runtime that contained the
pack less well than a container says so there, machine-readably, because that is the
[access tier](../scorecards/ceilings.md) argument applied to the runtime rather than to the
evaluation.

This is what makes a weaker backend acceptable to have at all. A subprocess runner that
claims `isolation: "container"` produces bundles that lie, and no amount of hashing fixes
that.

## `runtime_checkable` is not the contract

Worth knowing if you implement one.

`isinstance()` against this Protocol **passes a backend whose method signatures are
wrong.** It only fails on a missing method or a missing attribute. The real check is
`mypy --strict`, which the project runs over `src/`.

That is why `mypy` is configured the way it is: this Protocol is the reason it runs at all.

## `RunSpec`

What one unit of work is.

| Field | Notes |
|---|---|
| `run_id` | Unique within a run. `shutdown()` keys on it. |
| `pack_id`, `replicate` | Which pack, which repeat. |
| `image` | **Digest-pinned by freeze. A backend resolves nothing; a tag here is a bug upstream.** |
| `args`, `environment` | Passed to the container. |
| `output_dir` | Mounted read-write at `/output`. |
| `input_dir` | Mounted read-only at `/input` when set. |
| `egress` | Hosts the pack may reach. **Empty means deny all.** |
| `capture_stdout` | **Off by default.** A pack that logs a request logs the key with it. |
| `allow_unenforced_egress` | See below. |
| `timeout_seconds` | Optional. |
| `resources` | **Always set**, because a default that caps is safer than one that does not. |

## `RunResult`

| Field | Notes |
|---|---|
| `exit_code` | The pack's own verdict. Non-zero is a **result**, not a harness failure. |
| `image_digest` | **What actually ran, read back from the runtime** rather than from the plan. |
| `backend`, `isolation` | Carried into the bundle. |
| `egress_enforced` | `None` = declared nothing and had no network. `True` = allowlist enforced. `False` = declared, granted whole, not enforced. |
| `termination` | `timeout`, `out_of_memory`, `cancelled`, or `None`. |
| `native_id` | The runtime's own handle, for operators reading logs. **Nothing in the evidence path may depend on it.** |
| `started_utc`, `finished_utc` | |
| `stdout_path` | Set only when the spec asked for it. |

### Why `termination` is separate from `exit_code`

Docker reports 137 for a killed container, a timeout reports 137, and so does plain
SIGKILL. An exit code alone cannot carry the distinction, so it is a field.

A non-zero `exit_code` with no `termination` is the pack's own verdict and is a result, not
a harness failure.

## `resolve_digest` and `extract_manifest`

The two methods that make `freeze` possible.

`resolve_digest` turns a tag into the bytes it currently points at. `extract_manifest` reads
the pack's own declaration out of the image, so what it may reach is pinned from the image
rather than from a file next to it.

`extract_manifest` returning `None` means the image carries no manifest, and `freeze`
refuses it: what the pack may reach would be unpinnable.

## `allow_unenforced_egress`

Off by default. It stays in the spec for two reasons:

1. **A backend that cannot contain a pack has to be able to say so**, and to record it in
   the bundle.
2. A pack being built against an API it has not finished declaring needs a way to run.

On the docker backend it is a downgrade rather than a way to run at all, because that
backend enforces the allowlist. See [Containment](../running/containment.md).

## Errors

A pack exiting non-zero is a result, reported in `RunResult.exit_code`, and the caller
decides what it means.

A backend that cannot do its job at all raises `BackendError`.

## Writing one

Implement the seven methods, set `name` and `isolation` truthfully, and run
`mypy --strict` over it. There is no registration step in 0.1.0, because the backend is
constructed by the CLI, so a third-party backend currently means a fork or a patch.

A plugin entry point is on the list. See [Status](../project/status.md).
