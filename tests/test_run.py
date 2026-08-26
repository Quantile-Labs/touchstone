"""Running a frozen plan, and refusing an unfrozen one.

The backend is a stub, so these cover the orchestration and the ledger without a daemon.
tests/test_docker_backend.py covers the container itself.
"""

import json
from pathlib import Path

import pytest
from conftest import DIGEST, StubBackend

from touchstone import freeze as freeze_plan
from touchstone import run as run_plan
from touchstone.errors import PlanError


def ledger(out_dir: Path) -> list[dict]:
    path = out_dir / run_plan.LEDGER_DIR / run_plan.RUNLOG_NAME
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_runs_one_unit_per_replicate(frozen, tmp_path):
    backend = StubBackend()
    assert run_plan.run(frozen, tmp_path / "out", backend) == []
    assert [spec.run_id for spec in backend.seen] == ["example_pack-0", "example_pack-1"]


def test_each_unit_gets_its_own_seed_from_the_lock(frozen, tmp_path):
    backend = StubBackend()
    run_plan.run(frozen, tmp_path / "out", backend)
    seeds = [json.loads(spec.args[3])["seed"] for spec in backend.seen]
    assert seeds == [freeze_plan.derive_seed(7, "example_pack", n) for n in (0, 1)]
    assert len(set(seeds)) == 2


def test_the_pack_is_told_its_replicate(frozen, tmp_path):
    backend = StubBackend()
    run_plan.run(frozen, tmp_path / "out", backend)
    assert [json.loads(spec.args[3])["replicate"] for spec in backend.seen] == [0, 1]


def test_the_image_run_is_the_pinned_digest(frozen, tmp_path):
    backend = StubBackend()
    run_plan.run(frozen, tmp_path / "out", backend)
    assert {spec.image for spec in backend.seen} == {DIGEST}


def test_records_from_every_unit_end_up_in_one_file(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    assert len((out / run_plan.ITEMS_NAME).read_text().splitlines()) == 2


def test_the_ledger_opens_with_the_plan_hash(frozen, tmp_path):
    """The anchor and the run are tied together by the harness, at run start."""
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    first = ledger(out)[0]
    assert first["event"] == "run_started"
    assert first["plan_hash"] == freeze_plan.recorded_hash(frozen)


def test_the_ledger_records_every_unit(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    events = [entry["event"] for entry in ledger(out)]
    assert events == [
        "run_started",
        "unit_started",
        "unit_finished",
        "unit_started",
        "unit_finished",
        "run_finished",
    ]


def test_a_failing_unit_is_reported_and_logged(frozen, tmp_path):
    out = tmp_path / "out"
    failures = run_plan.run(frozen, out, StubBackend(exit_code=1))
    assert len(failures) == 2
    assert ledger(out)[-1]["failures"] == 2


def test_a_timeout_is_named_in_the_failure(frozen, tmp_path):
    failures = run_plan.run(
        frozen, tmp_path / "out", StubBackend(exit_code=137, termination="timeout")
    )
    assert all("timeout" in failure for failure in failures)


def test_refuses_a_plan_that_was_never_frozen(tmp_path):
    (tmp_path / "lock").mkdir()
    with pytest.raises(PlanError, match="freeze"):
        run_plan.run(tmp_path / "lock", tmp_path / "out", StubBackend())


def test_refuses_a_lock_edited_after_freezing(frozen, tmp_path):
    path = frozen / freeze_plan.LOCK_NAME
    record = json.loads(path.read_text())
    record["packs"][0]["seeds"][0] = 1
    path.write_text(json.dumps(record))

    with pytest.raises(PlanError, match="changed since it was frozen"):
        run_plan.run(frozen, tmp_path / "out", StubBackend())


def test_nothing_runs_when_the_lock_is_refused(frozen, tmp_path):
    (frozen / freeze_plan.LOCK_NAME).write_text("{}")
    backend = StubBackend()
    with pytest.raises(PlanError):
        run_plan.run(frozen, tmp_path / "out", backend)
    assert backend.seen == []


def test_freezing_and_running_into_one_directory_keeps_the_plan(tmp_path):
    """The README's own sequence. The plan is already in place, so there is nothing to
    copy, and raising here discarded a run whose packs had already finished."""
    (tmp_path / run_plan.LOCK_NAME).write_text('{"lock_format": 1}')
    (tmp_path / run_plan.HASH_NAME).write_text("hash\n")

    run_plan.copy_plan(tmp_path, tmp_path)

    assert (tmp_path / run_plan.LOCK_NAME).read_text() == '{"lock_format": 1}'
    assert (tmp_path / run_plan.HASH_NAME).read_text() == "hash\n"


def test_the_plan_is_copied_when_the_run_lands_elsewhere(tmp_path):
    lock_dir, out_dir = tmp_path / "lock", tmp_path / "out"
    lock_dir.mkdir()
    (lock_dir / run_plan.LOCK_NAME).write_text('{"lock_format": 1}')
    (lock_dir / run_plan.HASH_NAME).write_text("hash\n")

    run_plan.copy_plan(lock_dir, out_dir)

    assert (out_dir / run_plan.LOCK_NAME).read_text() == '{"lock_format": 1}'
    assert (out_dir / run_plan.HASH_NAME).read_text() == "hash\n"
