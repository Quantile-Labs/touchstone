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
from touchstone.contracts import Environment
from touchstone.errors import BackendError, PlanError


def ledger(out_dir: Path) -> list[dict]:
    path = out_dir / run_plan.LEDGER_DIR / run_plan.RUNLOG_NAME
    return [json.loads(line) for line in path.read_text().splitlines()]


def cost_of(out_dir: Path):
    path = out_dir / run_plan.ENVIRONMENT_NAME
    return Environment.model_validate_json(path.read_text()).cost


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


def test_the_ledger_records_how_long_each_unit_took(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    finished = [entry for entry in ledger(out) if entry["event"] == "unit_finished"]
    assert len(finished) == 2
    assert all(entry["wall_seconds"] >= 0 for entry in finished)


def test_the_environment_totals_the_wall_time_the_ledger_records(frozen, tmp_path):
    """Two records of one fact, written at different moments, so they had better agree."""
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    per_unit = [entry["wall_seconds"] for entry in ledger(out) if "wall_seconds" in entry]
    cost = cost_of(out)

    assert cost.wall_seconds == pytest.approx(sum(per_unit), abs=1e-3)
    assert [(pack.pack_id, pack.units) for pack in cost.packs] == [("example_pack", 2)]


def test_a_pack_that_reports_no_cost_is_recorded_as_reporting_none(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    [pack] = cost_of(out).packs
    assert (pack.items, pack.items_costed, pack.totals) == (2, 0, {})


def test_the_cost_on_each_row_is_summed_within_its_pack(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend(cost={"input_tokens": 120, "output_tokens": 30}))
    [pack] = cost_of(out).packs
    assert pack.items_costed == 2
    assert pack.totals == {"input_tokens": 240.0, "output_tokens": 60.0}


def test_a_cost_that_is_not_figures_counts_as_none_and_the_run_still_finishes(frozen, tmp_path):
    """A malformed row is `estimate`'s to refuse. Raising here would discard a run whose
    packs had already finished, which is the failure `copy_plan` once caused."""
    out = tmp_path / "out"
    assert run_plan.run(frozen, out, StubBackend(cost={"tokens": "many"})) == []

    [pack] = cost_of(out).packs
    assert (pack.items_costed, pack.totals) == (0, {})
    assert ledger(out)[-1]["event"] == "run_finished"


class UnreachableBackend(StubBackend):
    def run(self, spec):
        self.seen.append(spec)
        raise BackendError("the daemon went away")


def test_a_unit_that_failed_still_counts_toward_what_the_run_took(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, UnreachableBackend())

    failed = [entry for entry in ledger(out) if entry["event"] == "unit_failed"]
    assert len(failed) == 2
    assert all("wall_seconds" in entry for entry in failed)
    [pack] = cost_of(out).packs
    assert (pack.units, pack.items) == (2, 0)


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
