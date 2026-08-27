---
title: Anchoring
description: >-
  Timestamping the plan hash with OpenTimestamps, and being honest about what a
  fresh receipt actually proves.
---

# Anchoring

```console
$ touchstone freeze examples/plan.yaml -o ./run-004 --anchor
```

Stamps the plan hash with [OpenTimestamps](https://opentimestamps.org/), so a claim about
**when a run was designed** can be checked.
{ .lede }

## What it is for

A bundle hash proves the files have not changed since sealing. It does not prove when they
were sealed, and it does not prove the thresholds were fixed before the numbers were known.

That second one is the thing an auditor actually wants. A grade boundary chosen after
seeing the result is not a boundary, and the only way to rule it out from outside the
organisation is a timestamp the organisation did not issue.

Anchoring the **plan** hash is what does that. It puts the thresholds in time, before the
run.

## What lands in the bundle

```text
run-004/anchors/
├── PLAN.sha256          a copy of the hash file that was stamped
├── PLAN.sha256.ots      the OpenTimestamps receipt
└── README.md            what the receipt proves, written into the bundle
```

The hash file is copied into `anchors/` so **the directory verifies on its own**, without
reference to the rest of the bundle.

## Checking it

```console
$ ots verify PLAN.sha256.ots
```

## A fresh receipt proves less than it looks like it proves

This is written into `anchors/README.md` inside every anchored bundle, rather than left for
the reader to find out.

!!! danger "Immediately after stamping, the receipt is a calendar server's promise, not a bitcoin confirmation."

    It becomes a bitcoin attestation once the transaction confirms, usually within a few
    hours, and **the receipt has to be upgraded to carry that proof**:

    ```console
    $ ots upgrade PLAN.sha256.ots
    ```

    Until that is done and the upgraded file is put back in the directory, the anchor rests
    on the calendar servers rather than on a blockchain.

```console
$ ots info PLAN.sha256.ots
```

says which of the two you are holding.

**Upgrading is a step somebody has to remember.** If you anchor, put the upgrade in whatever
process seals and publishes the bundle, hours or days later. An un-upgraded receipt in a
published bundle is a weaker claim than it appears, and the person relying on it will not
usually check.

## `ots` is not a dependency

Anchoring shells out to the `ots` binary rather than depending on the OpenTimestamps client
library, which would put a bitcoin stack in the dependency closure of `touchstone verify`.

Same reasoning as the Docker backend: the check has to stay small enough that anyone can
run it.

```console
$ pip install opentimestamps-client
```

If `ots` is not on `PATH`, `--anchor` fails with that instruction rather than silently
skipping the stamp. Freeze without `--anchor` if you do not want it.

## Needs network

`freeze --anchor` is the only part of `freeze` that does. Everything else about the command,
and every command after `run`, is offline.
