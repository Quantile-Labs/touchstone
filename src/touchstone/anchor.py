# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Timestamp the plan hash, so a claim about when a run was designed can be checked.

Shells out to `ots` rather than depending on the OpenTimestamps client, which would put a
bitcoin stack in the dependency closure of `touchstone verify`. Same reasoning as the
docker backend.

A fresh receipt proves less than it looks like it proves, and this module says so in the
bundle rather than leaving the reader to find out. See the note written into anchors/.
"""

import shutil
import subprocess
from pathlib import Path

from touchstone.errors import AnchorError

ANCHORS_DIR = "anchors"
NOTE_NAME = "README.md"

NOTE = """# Anchors

`PLAN.sha256` is a copy of the hash file that was stamped, kept here so this directory
verifies on its own.

`PLAN.sha256.ots` is an OpenTimestamps receipt for it.

## Checking it

```
ots verify PLAN.sha256.ots
```

## What a fresh receipt proves

**Immediately after stamping, this receipt is a calendar server's promise, not a bitcoin
confirmation.** It becomes a bitcoin attestation once the transaction confirms, usually
within a few hours, and the receipt has to be upgraded to carry that proof:

```
ots upgrade PLAN.sha256.ots
```

Until that is done and the upgraded file is put back in this directory, the anchor rests
on the calendar servers rather than on a blockchain. `ots info PLAN.sha256.ots` says which
of the two you are holding.
"""


def stamp(hash_path: Path, bundle_dir: Path, binary: str = "ots") -> Path:
    """Copy the hash file into anchors/ and timestamp it there. Returns the receipt."""
    if not hash_path.is_file():
        raise AnchorError(f"nothing to stamp: {hash_path} does not exist")

    anchors = bundle_dir / ANCHORS_DIR
    anchors.mkdir(parents=True, exist_ok=True)
    stamped = anchors / hash_path.name
    shutil.copyfile(hash_path, stamped)

    try:
        done = subprocess.run(
            [binary, "stamp", stamped.name], cwd=anchors, capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise AnchorError(
            f"{binary} is not on PATH. Install the OpenTimestamps client with "
            "`pip install opentimestamps-client`, or freeze without --anchor"
        ) from exc

    receipt = anchors / f"{stamped.name}.ots"
    if done.returncode != 0 or not receipt.is_file():
        raise AnchorError(f"{binary} stamp failed: {done.stderr.strip() or 'no receipt written'}")

    (anchors / NOTE_NAME).write_text(NOTE)
    return receipt
