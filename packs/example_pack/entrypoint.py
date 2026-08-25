#!/usr/bin/env python3
"""Emit one observation per item. The smallest pack that exercises the whole path.

Deterministic on purpose: the same seed and replicate produce a byte-identical
items.jsonl. ASQI's mock_tester draws an unseeded random score, which is fine for testing
an executor and useless for testing a tool whose subject is reproducibility.

Standard library only, so the image needs no wheels and builds without an index.
"""

import argparse
import json
import random
import sys
from pathlib import Path

DEFAULT_OUTPUT = Path("/output")
DEFAULT_ITEMS = 10

LANGUAGES = ["en", "pcm", "ha", "yo", "ig"]
DIFFICULTIES = ["single_step", "multi_step"]


def observations(count: int, seed: int, replicate: int) -> list[dict]:
    """Build count records. Same arguments, same records, on any machine."""
    rng = random.Random(f"example_pack:{seed}:{replicate}")
    records = []
    for index in range(count):
        records.append(
            {
                "item_id": f"example.{index:04d}",
                "stratum": {
                    "language": LANGUAGES[index % len(LANGUAGES)],
                    "difficulty": DIFFICULTIES[index % len(DIFFICULTIES)],
                },
                "outcome": {"correct": rng.random() < 0.72},
                "score": {"quality": round(rng.uniform(0.2, 1.0), 4)},
                "confidence": round(rng.uniform(0.5, 1.0), 4),
                "replicate": replicate,
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal pack that emits item records.")
    parser.add_argument("--systems-params", required=True)
    parser.add_argument("--test-params", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        systems = json.loads(args.systems_params)
        params = json.loads(args.test_params)
    except json.JSONDecodeError as exc:
        print(f"malformed parameters: {exc}", file=sys.stderr)
        return 2

    if "system_under_test" not in systems:
        print("no system_under_test in systems params", file=sys.stderr)
        return 2

    records = observations(
        count=params.get("max_items", DEFAULT_ITEMS),
        seed=params.get("seed", 0),
        replicate=params.get("replicate", 0),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "items.jsonl").open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    # stdout is logs, never results. 02-DESIGN.md section 7.4.
    print(f"wrote {len(records)} item record(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
