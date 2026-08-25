"""Shared stubs. Orchestration is tested without a daemon; the container has its own file."""

import json
from pathlib import Path

import pytest

from touchstone import freeze as freeze_plan
from touchstone.backends.base import RunResult, RunSpec
from touchstone.contracts import Manifest, Plan
from touchstone.contracts.manifest import Network

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

    def __init__(self, exit_code: int = 0, termination: str | None = None, egress=()):
        self.exit_code = exit_code
        self.termination = termination
        self.egress = list(egress)
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
        return Manifest(name="example_pack", version="1.0", network=Network(egress=self.egress))

    def resolve_digest(self, image: str) -> str:
        return DIGEST


@pytest.fixture
def frozen(tmp_path) -> Path:
    lock_dir = tmp_path / "lock"
    freeze_plan.write_lock(freeze_plan.freeze(Plan.model_validate(PLAN), StubBackend()), lock_dir)
    return lock_dir
