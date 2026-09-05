"""Shared stubs. Orchestration is tested without a daemon; the container has its own file."""

import json
from pathlib import Path

import pytest

from touchstone import freeze as freeze_plan
from touchstone.backends.base import RunResult, RunSpec
from touchstone.contracts import Manifest, Plan
from touchstone.contracts.manifest import Network, Resources

DIGEST = "example/example_pack@sha256:" + "c" * 64

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
            "params": {"max_items": 2},
            "replicates": 2,
        }
    ],
}


class StubBackend:
    name = "stub"
    isolation = "none"

    def __init__(
        self, exit_code: int = 0, termination: str | None = None, egress=(), resources=None
    ):
        self.exit_code = exit_code
        self.termination = termination
        self.egress = list(egress)
        self.resources = resources or Resources()
        self.seen: list[RunSpec] = []

    def run(self, spec: RunSpec) -> RunResult:
        self.seen.append(spec)
        spec.output_dir.mkdir(parents=True, exist_ok=True)
        record = {"item_id": f"{spec.pack_id}.{spec.replicate}", "replicate": spec.replicate}
        (spec.output_dir / "items.jsonl").write_text(json.dumps(record) + "\n")
        return RunResult(
            run_id=spec.run_id,
            exit_code=self.exit_code,
            image_digest=DIGEST,
            backend=self.name,
            isolation=self.isolation,
            started_utc="2026-08-25T00:00:00Z",
            finished_utc="2026-08-25T00:00:01Z",
            termination=self.termination,
        )

    def shutdown(self, run_ids): ...
    def check_images(self, images): ...
    def pull_images(self, images): ...
    def extract_manifest(self, image, manifest_path=""):
        return Manifest(
            name="example_pack",
            version="1.0",
            network=Network(egress=self.egress),
            resources=self.resources,
        )

    def resolve_digest(self, image: str) -> str:
        return DIGEST


@pytest.fixture
def frozen(tmp_path) -> Path:
    lock_dir = tmp_path / "lock"
    freeze_plan.write_lock(freeze_plan.freeze(Plan.model_validate(PLAN), StubBackend()), lock_dir)
    return lock_dir


ESTIMATES = {
    "touchstone_version": "test",
    "items": 400,
    "packs": ["example_pack"],
    "pooled": False,
    "estimates": [
        {
            "metric": "correct",
            "pack_id": "example_pack",
            "stratum": {},
            "n": 400,
            "point": 0.91,
            "low": 0.8783,
            "high": 0.9345,
            "k": 364,
            "estimator": "wilson",
            "parameters": {"z": 1.959963984540054},
            "reference": "Wilson 1927",
        }
    ],
}

LOCK = {
    "lock_format": 3,
    "plan_name": "example",
    "access_tier": "black_box",
    "root_seed": 7,
    "systems": {},
    "packs": [
        {
            "id": "example_pack",
            "image": "example_pack@sha256:" + "a" * 64,
            "calibrates": None,
            "emits_items": True,
            "seeds": [1],
        }
    ],
}

SCORE_CARD = """
score_card_name: "DQI test card"
levels: ["A", "B", "C", "D", "E", "F", "G", "H"]
tier_ceilings:
  black_box: "A"
indicators:
  - id: headline_accuracy
    name: "Headline accuracy with interval"
    metric: {source: estimate, name: correct, pack_id: example_pack}
    assessment:
      - {level: "A", condition: greater_equal_ci_lower, threshold: 0.90}
      - {level: "C", condition: greater_equal_ci_lower, threshold: 0.70}
"""


@pytest.fixture
def graded(tmp_path) -> tuple[Path, Path]:
    """A run directory holding estimates and a lock, and a score card to apply to it.

    Here rather than in one test module because two of them grade a run now, and a test
    importing another test module works only while the repository root happens to be on
    `sys.path`. It is on a laptop and it is not in CI.
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "estimates.json").write_text(json.dumps(ESTIMATES))
    (run_dir / "plan.lock.json").write_text(json.dumps(LOCK))
    (run_dir / "PLAN.sha256").write_text("2005a468" + "0" * 56 + "  plan.lock.json\n")
    card = tmp_path / "card.yaml"
    card.write_text(SCORE_CARD)
    return run_dir, card
