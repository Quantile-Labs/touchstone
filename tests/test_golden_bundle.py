"""A frozen bundle, recomputed and byte-compared. See tests/golden/README.md.

03-BUILD-PLAN.md section 6 asks for this against an estimator change silently altering a
published number. The stats tests pin the arithmetic. What they cannot see is the
serialisation: a renamed field, a dropped parameter or a different float repr leaves every
unit test green and breaks the one thing a bundle promises, which is that a client can
re-read it years later and get the same numbers back.
"""

import json
import re
from pathlib import Path

from touchstone import bundle
from touchstone.estimate import ESTIMATES_NAME, estimate, load_items, write_estimates

GOLDEN = Path(__file__).parent / "golden" / "run-001"
SETTINGS = json.loads(GOLDEN.with_suffix(".json").read_text())
VERSION = re.compile(r'"touchstone_version": "[^"]*"')


def _version_agnostic(text: str) -> str:
    """The estimates with the version they were computed under blanked out."""
    normalised, substitutions = VERSION.subn('"touchstone_version": "frozen"', text)
    assert substitutions == 1, "estimates.json no longer names the version that computed it"
    return normalised


def test_the_golden_bundle_still_verifies():
    assert bundle.verify(GOLDEN) == []


def test_estimates_serialise_the_way_the_golden_bundle_recorded(tmp_path):
    write_estimates(estimate(load_items(GOLDEN / "items.jsonl"), **SETTINGS), tmp_path)

    recomputed = (tmp_path / ESTIMATES_NAME).read_text()
    frozen = (GOLDEN / ESTIMATES_NAME).read_text()
    assert _version_agnostic(recomputed) == _version_agnostic(frozen)
