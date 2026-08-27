---
title: Verifying a bundle
description: >-
  Checking a bundle with one offline command, or with shasum alone, and exactly
  what that check does and does not catch.
---

# Verifying a bundle

```console
$ touchstone verify ./run-004
./run-004: verified
```

Walks every file in the manifest and exits non-zero on the first mismatch. **Offline**, no
Docker, no network.
{ .lede }

## Without this tool

The bundle should outlive the tool, so every check it does is one you can do by hand.

**Check one file against its recorded hash:**

```console
$ shasum -a 256 run-004/items.jsonl
fc127dc53abc97b4528d666a732707ca5b010dd108713ad830e540e0d3d932b0  run-004/items.jsonl
```

Compare that against the entry in `MANIFEST.json`.

**Recompute the bundle hash from the manifest:**

```console
$ jq -cS '.files' run-004/MANIFEST.json | tr -d '\n' | shasum -a 256
dd02c96f00ed44c64c2bd4867d86d03ae7155ddf720cb8e45c628409b4692bba  -
```

**Check the plan hash:**

```console
$ cd run-004 && shasum -a 256 -c PLAN.sha256
plan.lock.json: OK
```

Every file in the manifest, in a loop:

```bash
cd run-004
jq -r '.files[] | "\(.sha256)  \(.path)"' MANIFEST.json | shasum -a 256 -c
```

## What `verify` checks

1. `MANIFEST.json` parses and validates.
2. Every path in it stays inside the bundle root.
3. Every file listed exists, is the recorded size, and hashes to the recorded digest.
4. The bundle hash recomputes from the file list.

Any failure exits non-zero.

## What it does not catch

!!! danger "It catches a file changed after sealing. It does not catch someone who re-seals the whole thing and redoes the hashes."

    Nothing in a self-contained folder can. The hashes are computed by whoever ran
    `bundle`, and whoever can run it once can run it twice.

For that you need a timestamp from outside: `freeze --anchor` stamps the plan hash with
OpenTimestamps, proving the plan existed before the run. See [Anchoring](anchoring.md).

And **nothing stops someone running an evaluation ten times and sealing the run they
liked.** Run selection leaves no trace in any artefact this tool produces. Closing that
takes a commitment made in advance to publish every run against a plan. That is a process
somebody keeps, and `shasum` cannot check it. See [What this does not
prove](../project/limits.md).

## Verifying on a plane

This is a design constraint. `verify` needs no network, no Docker, no registry and no
database. The whole dependency closure of the check is Python and three packages.

Someone deciding whether to act on a result should be able to check it wherever they are,
including inside an organisation whose network will not let them reach a registry.
