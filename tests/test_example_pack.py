"""The mock pack, run as a subprocess the way a container runs it.

Every record it writes is parsed with the real ItemRecord contract, so the pack and the
engine cannot drift apart quietly. Determinism is checked across separate processes
rather than within one, because a seed that only holds inside a single interpreter is
not a seed.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from touchstone.contracts import ItemRecord
from touchstone.plan_check import load_manifest

PACK = Path(__file__).resolve().parents[1] / "packs" / "example_pack"
ENTRYPOINT = PACK / "entrypoint.py"
SYSTEMS = json.dumps({"system_under_test": {"type": "llm_api", "model": "example"}})


def run(output_dir: Path, systems: str = SYSTEMS, **params) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "--systems-params",
            systems,
            "--test-params",
            json.dumps(params),
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
    )


def records(output_dir: Path) -> list[ItemRecord]:
    lines = (output_dir / "items.jsonl").read_text().splitlines()
    return [ItemRecord.model_validate_json(line) for line in lines]


def test_emits_ten_records_that_the_contract_accepts(tmp_path):
    assert run(tmp_path).returncode == 0
    assert len(records(tmp_path)) == 10


def test_every_record_carries_the_strata_the_manifest_declares(tmp_path):
    run(tmp_path)
    declared = {stratum.name for stratum in load_manifest(PACK / "manifest.yaml").strata}
    for record in records(tmp_path):
        assert set(record.stratum) == declared


def test_the_same_seed_gives_a_byte_identical_file(tmp_path):
    run(tmp_path / "a", seed=7)
    run(tmp_path / "b", seed=7)
    assert (tmp_path / "a" / "items.jsonl").read_bytes() == (
        tmp_path / "b" / "items.jsonl"
    ).read_bytes()


def test_a_different_seed_gives_different_records(tmp_path):
    run(tmp_path / "a", seed=7)
    run(tmp_path / "b", seed=8)
    assert (tmp_path / "a" / "items.jsonl").read_bytes() != (
        tmp_path / "b" / "items.jsonl"
    ).read_bytes()


def test_a_replicate_is_not_a_rerun_of_the_same_numbers(tmp_path):
    run(tmp_path / "a", seed=7, replicate=0)
    run(tmp_path / "b", seed=7, replicate=1)
    assert (tmp_path / "a" / "items.jsonl").read_bytes() != (
        tmp_path / "b" / "items.jsonl"
    ).read_bytes()
    assert all(record.replicate == 1 for record in records(tmp_path / "b"))


def test_max_items_is_honoured(tmp_path):
    run(tmp_path, max_items=3)
    assert len(records(tmp_path)) == 3


def test_results_do_not_go_to_stdout(tmp_path):
    """02-DESIGN.md section 7.4. A pack that logs a request logs the key with it."""
    result = run(tmp_path)
    assert "item_id" not in result.stdout


@pytest.mark.parametrize(
    "systems", ['{"judge": {}}', "not json at all"], ids=["no_sut", "malformed"]
)
def test_fails_closed_on_bad_systems_params(tmp_path, systems):
    result = run(tmp_path, systems=systems)
    assert result.returncode != 0
    assert not (tmp_path / "items.jsonl").exists()
