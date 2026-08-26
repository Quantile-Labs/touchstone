#!/usr/bin/env python3
"""Recompute and reseal tests/golden/run-001. See tests/golden/README.md."""

import json
import sys
from pathlib import Path

from touchstone import bundle
from touchstone.estimate import estimate, load_items, write_estimates

GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "golden" / "run-001"


def main() -> int:
    settings = json.loads(GOLDEN.with_suffix(".json").read_text())
    items = load_items(GOLDEN / "items.jsonl")

    (GOLDEN / bundle.MANIFEST_NAME).unlink(missing_ok=True)
    write_estimates(estimate(items, **settings), GOLDEN)
    manifest = bundle.seal(GOLDEN)

    print(f"{GOLDEN}: {len(manifest.files)} file(s), sha256 {manifest.sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
