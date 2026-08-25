"""Declared egress: refused by default, grantable on purpose, recorded either way.

The backend cannot restrict a container to a host list without a proxy that does not exist
yet. The safe reading of an unenforceable allowlist is no, so no is the default. The
override exists because a pack that cannot reach an API cannot be built against one, and
its whole job is to leave a mark in the bundle that a grader can read.
"""

import json

import pytest
from conftest import PLAN, StubBackend

from touchstone import freeze as freeze_plan
from touchstone import run as run_plan
from touchstone.backends.base import RunResult, RunSpec
from touchstone.contracts import Environment, Plan


def test_egress_declared_in_a_manifest_is_pinned_into_the_lock(tmp_path):
    backend = StubBackend(egress=["api.example.com"])
    lock = freeze_plan.freeze(Plan.model_validate(PLAN), backend)
    assert lock.packs[0].egress == ["api.example.com"]


def test_the_spec_refuses_by_default():
    spec = RunSpec(
        run_id="a", pack_id="p", image="i", output_dir="/tmp/x", egress=["api.example.com"]
    )
    assert spec.allow_unenforced_egress is False


def test_a_run_without_egress_reports_nothing_to_report(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    environment = Environment.model_validate_json((out / run_plan.ENVIRONMENT_NAME).read_text())
    assert environment.egress_enforced is None


def test_the_environment_records_that_egress_was_not_enforced(tmp_path):
    """The mark a grader reads. Without it the override would be a silent downgrade."""
    result = RunResult(
        run_id="a",
        exit_code=0,
        image_digest="i@sha256:" + "a" * 64,
        backend="stub",
        isolation="none",
        started_utc="2026-08-25T00:00:00Z",
        finished_utc="2026-08-25T00:00:01Z",
        egress_enforced=False,
    )
    assert run_plan._overall_egress([result]) is False


def test_one_unenforced_unit_weakens_the_whole_run():
    def result(enforced):
        return RunResult(
            run_id="a",
            exit_code=0,
            image_digest="i@sha256:" + "a" * 64,
            backend="stub",
            isolation="none",
            started_utc="2026-08-25T00:00:00Z",
            finished_utc="2026-08-25T00:00:01Z",
            egress_enforced=enforced,
        )

    assert run_plan._overall_egress([result(True), result(False)]) is False
    assert run_plan._overall_egress([result(True), result(True)]) is True
    assert run_plan._overall_egress([result(None), result(False)]) is False


def test_the_environment_names_what_actually_ran(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    environment = Environment.model_validate_json((out / run_plan.ENVIRONMENT_NAME).read_text())
    assert environment.backend == "stub"
    assert all("@sha256:" in digest for digest in environment.image_digests)
    assert environment.plan_hash


def test_the_ledger_carries_the_same_fact(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    lines = (out / run_plan.LEDGER_DIR / run_plan.RUNLOG_NAME).read_text().splitlines()
    finished = [json.loads(line) for line in lines if json.loads(line)["event"] == "run_finished"]
    assert "egress_enforced" in finished[0]


@pytest.mark.parametrize("granted", [False, True])
def test_the_flag_reaches_the_backend(frozen, tmp_path, granted):
    backend = StubBackend()
    run_plan.run(frozen, tmp_path / "out", backend, allow_unenforced_egress=granted)
    assert all(spec.allow_unenforced_egress is granted for spec in backend.seen)
