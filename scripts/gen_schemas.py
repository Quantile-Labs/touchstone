#!/usr/bin/env python3
"""Regenerate the JSON Schemas in docs/schemas from the contracts. See
docs/reference/schemas.md.

Four files in this project are written by a person rather than by the tool: a plan, a
score card, a pack manifest and a set of audit responses. Each one already has a pydantic
model that decides whether it is valid. Generating the schema from that model means an
editor and `touchstone validate` agree by construction, and a schema hand-written beside
the contracts would be a second answer to the same question that drifts on the first
change nobody remembers to mirror.

`--check` compares the committed files against a fresh generation and exits non-zero on
the first difference, which is what CI and tests/test_schemas.py run.
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from touchstone.contracts import Manifest, Plan
from touchstone.contracts.audit import AuditResponses
from touchstone.contracts.scorecard import ScoreCard

SCHEMAS = Path(__file__).resolve().parents[1] / "docs" / "schemas"

BASE_URL = "https://touchstone.quantilelabs.com/schemas"
"""Where mkdocs publishes docs/schemas. The URL a `$schema` modeline names, so it has to
keep resolving for as long as any plan in the wild points at it."""

DIALECT = "https://json-schema.org/draft/2020-12/schema"

# Filename stem, the model behind it, the title an editor shows, and what the file is.
# The titles say `pack manifest` and not `manifest`, because a bundle holds a MANIFEST.json
# that is a different thing and a reader hovering a key should not have to work out which.
AUTHORED: list[tuple[str, type[BaseModel], str, str]] = [
    (
        "plan",
        Plan,
        "Touchstone plan",
        "What to run, against which systems, and at which access tier. Read by "
        "`touchstone validate` and frozen by `touchstone freeze`.",
    ),
    (
        "scorecard",
        ScoreCard,
        "Touchstone score card",
        "The rubric as data: the ladder, its thresholds and the ceilings that stop a "
        "claim exceeding its evidence. Applied by `touchstone grade --score-card`.",
    ),
    (
        "pack-manifest",
        Manifest,
        "Touchstone pack manifest",
        "What a pack declares about itself: the systems and parameters it needs, the "
        "strata it emits, and the egress and resources it is allowed.",
    ),
    (
        "audit",
        AuditResponses,
        "Touchstone audit responses",
        "The levels a person assessed for the indicators no bundle can answer on its "
        "own, and the evidence behind each. Passed to `touchstone grade --audit`.",
    ),
]


def build(stem: str, model: type[BaseModel], title: str, description: str) -> str:
    """One schema, as the bytes that belong on disk."""
    body = model.model_json_schema()
    # Pydantic titles the root after the class and describes it from the class docstring.
    # Neither is written for somebody reading a YAML file, so both are replaced here.
    body.pop("title", None)
    body.pop("description", None)
    document = {
        "$schema": DIALECT,
        "$id": f"{BASE_URL}/{stem}.schema.json",
        "title": title,
        "description": description,
        **body,
    }
    # Sorted, so a pydantic release that reorders its output does not show up as a diff in
    # every schema and drown the one key that actually changed.
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    checking = "--check" in argv[1:]
    SCHEMAS.mkdir(parents=True, exist_ok=True)

    stale = []
    for stem, model, title, description in AUTHORED:
        path = SCHEMAS / f"{stem}.schema.json"
        wanted = build(stem, model, title, description)
        if checking:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != wanted:
                stale.append(path)
            continue
        path.write_text(wanted, encoding="utf-8")

    if checking:
        if stale:
            print(f"{len(stale)} schema(s) out of date with the contracts:", file=sys.stderr)
            for path in stale:
                print(f"  {path.relative_to(SCHEMAS.parents[1])}", file=sys.stderr)
            print("run: uv run python scripts/gen_schemas.py", file=sys.stderr)
            return 1
        print(f"{SCHEMAS}: {len(AUTHORED)} schema(s) up to date")
        return 0

    print(f"{SCHEMAS}: {len(AUTHORED)} schema(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
