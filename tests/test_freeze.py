"""Freezing a plan, and the properties an anchor depends on.

M1's completion test is that a hash from freeze matches one computed independently with
shasum, and that editing one character changes it. Both are here, and the shasum one
shells out to the real tool rather than reimplementing it in Python, because a hash only
this codebase can reproduce is not an anchor.
"""

import json
import subprocess
from pathlib import Path

import pytest

from touchstone import freeze as freeze_plan
from touchstone.contracts import Manifest, Plan
from touchstone.contracts.lock import PlanLock
from touchstone.contracts.manifest import Network
from touchstone.errors import PlanError

PLAN = {
    "plan_name": "demo",
    "access_tier": "black_box",
    "seed": 7,
    "systems": {"chatbot": {"type": "llm_api"}},
    "packs": [
        {
            "id": "example_pack",
            "image": "example/example_pack:1.0",
            "systems": {"system_under_test": "chatbot"},
            "params": {"max_items": 10},
            "replicates": 3,
        }
    ],
}

DIGEST = "example/example_pack@sha256:" + "b" * 64


class StubBackend:
    """Resolves a tag to a fixed digest. Freezing must not need a daemon to be tested."""

    name = "stub"
    isolation = "none"
    egress: list[str] = []

    def run(self, spec): ...
    def shutdown(self, run_ids): ...
    def check_images(self, images): ...
    def pull_images(self, images): ...
    def extract_manifest(self, image, manifest_path=""):
        return Manifest(name="example_pack", version="1.0", network=Network(egress=self.egress))

    def resolve_digest(self, image: str) -> str:
        return DIGEST


def frozen(**overrides) -> PlanLock:
    plan = Plan.model_validate(PLAN | overrides)
    return freeze_plan.freeze(plan, StubBackend())


def test_every_image_is_pinned_to_a_digest():
    lock = frozen()
    assert lock.packs[0].image == DIGEST


def test_a_tag_in_a_lock_is_rejected_by_the_contract():
    with pytest.raises(ValueError):
        PlanLock.model_validate(
            {
                "plan_name": "demo",
                "access_tier": "black_box",
                "root_seed": 0,
                "systems": {},
                "packs": [{"id": "p", "image": "example/p:1.0", "seeds": [0]}],
            }
        )


def test_one_seed_per_replicate():
    assert len(frozen().packs[0].seeds) == 3


def test_seeds_differ_between_replicates_and_between_packs():
    seeds = frozen().packs[0].seeds
    assert len(set(seeds)) == 3
    assert freeze_plan.derive_seed(7, "a", 0) != freeze_plan.derive_seed(7, "b", 0)


def test_seed_derivation_is_stable():
    """Pinned on purpose. If this number moves, every past run stops reproducing.

    Reproduce it without this codebase:
        printf '7:example_pack:0' | shasum -a 256 | cut -c1-16   # then hex to int
    """
    assert freeze_plan.derive_seed(7, "example_pack", 0) == 16110102871655720643


def test_freezing_the_same_plan_twice_gives_the_same_bytes():
    assert freeze_plan.lock_bytes(frozen()) == freeze_plan.lock_bytes(frozen())


def test_the_hash_matches_shasum(tmp_path):
    """The completion test for M1. shasum, not hashlib."""
    _, digest = freeze_plan.write_lock(frozen(), tmp_path)
    out = subprocess.run(
        ["shasum", "-a", "256", freeze_plan.LOCK_NAME],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert out.stdout.split()[0] == digest


def test_shasum_can_check_the_recorded_hash_file(tmp_path):
    """`shasum -a 256 -c PLAN.sha256` is the whole verification story for the anchor."""
    freeze_plan.write_lock(frozen(), tmp_path)
    out = subprocess.run(
        ["shasum", "-a", "256", "-c", freeze_plan.HASH_NAME],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_editing_one_character_changes_the_hash(tmp_path):
    before = freeze_plan.write_lock(frozen(), tmp_path)[1]
    after = freeze_plan.write_lock(frozen(plan_name="demo2"), tmp_path)[1]
    assert before != after


def test_a_different_root_seed_changes_the_hash(tmp_path):
    before = freeze_plan.write_lock(frozen(), tmp_path)[1]
    after = freeze_plan.write_lock(frozen(seed=8), tmp_path)[1]
    assert before != after


def test_check_frozen_accepts_an_untouched_lock(tmp_path):
    freeze_plan.write_lock(frozen(), tmp_path)
    freeze_plan.check_frozen(tmp_path)


def test_check_frozen_rejects_an_edited_lock(tmp_path):
    freeze_plan.write_lock(frozen(), tmp_path)
    path = tmp_path / freeze_plan.LOCK_NAME
    record = json.loads(path.read_text())
    record["packs"][0]["seeds"][0] = 1
    path.write_text(json.dumps(record))

    with pytest.raises(PlanError, match="changed since it was frozen"):
        freeze_plan.check_frozen(tmp_path)


def test_check_frozen_rejects_a_plan_that_was_never_frozen(tmp_path):
    with pytest.raises(PlanError, match="freeze"):
        freeze_plan.check_frozen(tmp_path)


def test_the_lock_carries_no_timestamp(tmp_path):
    """A timestamp would mean freezing the same plan twice gave two hashes."""
    record = json.loads(Path(freeze_plan.write_lock(frozen(), tmp_path)[0]).read_text())
    assert not [key for key in record if "utc" in key or "time" in key]
