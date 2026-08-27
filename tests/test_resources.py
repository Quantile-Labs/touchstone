"""The ceiling one pack runs under, from its manifest to the docker command line.

ASQI caps memory at 2g and CPU at two cores as a global default no pack can express a need
for. The defaults here match those figures deliberately, so a pack that declares nothing
behaves the same under both, and what is new is that a pack can say otherwise and a
reviewer can read the figure off the frozen plan.

These need no daemon. Whether the kernel actually enforces the cap is in
`tests/test_docker_backend.py`.
"""

import subprocess

import pytest
from conftest import PLAN, StubBackend

from touchstone import freeze as freeze_plan
from touchstone.backends.base import RunSpec
from touchstone.backends.docker import DockerBackend
from touchstone.contracts import Plan
from touchstone.contracts.manifest import Resources


def args_for(**resources) -> list[str]:
    """The docker command line a spec produces, without running anything."""
    backend = DockerBackend()
    seen: list[list[str]] = []

    def record(*args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
        seen.append(list(args))
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout="", stderr="")

    backend._cli = record  # type: ignore[method-assign]
    backend.resolve_digest = lambda image: f"{image}@sha256:{'a' * 64}"  # type: ignore[method-assign]
    backend.run(
        RunSpec(
            run_id="unit",
            pack_id="p",
            image="i",
            output_dir="/tmp/touchstone-args-test",
            resources=Resources(**resources) if resources else Resources(),
        )
    )
    return next(call for call in seen if call and call[0] == "run")


def value_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def termination_for(exit_code: int, tmp_path) -> str | None:
    """What a docker exit is recorded as, with no daemon and no OOM event to read."""
    backend = DockerBackend()

    def stub(*args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
        code = exit_code if args[0] == "run" else 0
        return subprocess.CompletedProcess(args=list(args), returncode=code, stdout="", stderr="")

    backend._cli = stub  # type: ignore[method-assign]
    backend.resolve_digest = lambda image: f"{image}@sha256:{'a' * 64}"  # type: ignore[method-assign]
    result = backend.run(
        RunSpec(run_id="unit", pack_id="p", image="i", output_dir=tmp_path / "out")
    )
    return result.termination


def test_the_defaults_match_the_figures_asqi_uses():
    limits = Resources()
    assert limits.memory_mb == 2048
    assert limits.cpus == 2.0


def test_a_pack_that_declares_nothing_is_still_capped():
    """A default that does not cap is not a default, it is an omission."""
    args = args_for()
    assert value_after(args, "--memory") == "2048m"
    assert value_after(args, "--pids-limit") == "512"


def test_swap_is_pinned_to_the_memory_limit():
    """Docker defaults --memory-swap to twice --memory. Left alone, a container given 2g
    reaches 4g through swap and the limit reads as enforced while it is not."""
    args = args_for(memory_mb=512)
    assert value_after(args, "--memory") == "512m"
    assert value_after(args, "--memory-swap") == "512m"


def test_a_pack_can_declare_more_than_the_default():
    args = args_for(memory_mb=8192, cpus=4.0, pids=1024)
    assert value_after(args, "--memory") == "8192m"
    assert value_after(args, "--cpus") == "4.0"
    assert value_after(args, "--pids-limit") == "1024"


@pytest.mark.parametrize("field,value", [("memory_mb", 32), ("cpus", 0), ("cpus", -1), ("pids", 4)])
def test_a_ceiling_too_low_to_run_anything_is_refused(field, value):
    with pytest.raises(ValueError):
        Resources(**{field: value})


def test_the_manifest_figure_is_pinned_into_the_lock():
    """Same reason as egress: a reviewer reads the ceiling off the frozen plan rather than
    off an image they would have to pull."""
    backend = StubBackend(resources=Resources(memory_mb=4096, cpus=1.0))
    lock = freeze_plan.freeze(Plan.model_validate(PLAN), backend)

    assert lock.packs[0].resources.memory_mb == 4096
    assert lock.packs[0].resources.cpus == 1.0
    assert lock.lock_format >= 4, "adding resources to the lock has to move the plan hash"


def test_a_pack_declaring_nothing_still_lands_a_ceiling_in_the_lock():
    lock = freeze_plan.freeze(Plan.model_validate(PLAN), StubBackend())
    assert lock.packs[0].resources.memory_mb == 2048


def test_a_kill_under_the_cap_is_named_without_asking_docker_why(tmp_path):
    """dockerd writes `State.OOMKilled` from an event containerd delivers, and on cgroup v2
    that event goes missing: this test's stub answers nothing, and CI has seen a real
    container exit 137 against a 64m cap with the flag false. A kill recorded as no
    termination is the pack's own exit code by the rule in `RunResult`, which hands the
    system under test the blame for a ceiling the harness imposed."""
    assert termination_for(137, tmp_path) == "out_of_memory"


def test_a_pack_that_fails_on_its_own_is_not_read_as_a_kill(tmp_path):
    assert termination_for(1, tmp_path) is None
    assert termination_for(0, tmp_path) is None
