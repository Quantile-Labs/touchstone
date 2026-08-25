"""The docker backend, against a real daemon.

Skipped when no daemon is reachable, so a laptop with Docker closed still runs the suite.
That makes the CI job in `.github/workflows/ci.yml` the thing that keeps these honest:
a backend whose tests only ever skip is a backend nobody has tested.
"""

import json
import subprocess
from pathlib import Path

import pytest

from touchstone.backends import DockerBackend, RunSpec
from touchstone.contracts import ItemRecord
from touchstone.errors import BackendError

PACK = Path(__file__).resolve().parents[1] / "packs" / "example_pack"
IMAGE = "touchstone-example-pack:test"
SYSTEMS = json.dumps({"system_under_test": {"type": "llm_api"}})


def daemon_is_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


pytestmark = pytest.mark.skipif(not daemon_is_up(), reason="no docker daemon")


@pytest.fixture(scope="module")
def image() -> str:
    subprocess.run(
        ["docker", "build", "-q", "-t", IMAGE, str(PACK)], check=True, capture_output=True
    )
    return IMAGE


@pytest.fixture
def backend() -> DockerBackend:
    return DockerBackend()


def spec(tmp_path: Path, image: str, **overrides) -> RunSpec:
    defaults = {
        "run_id": "example-pack-0",
        "pack_id": "example_pack",
        "image": image,
        "args": ["--systems-params", SYSTEMS, "--test-params", '{"max_items": 10, "seed": 7}'],
        "output_dir": tmp_path / "out",
    }
    return RunSpec(**(defaults | overrides))


def test_runs_a_pack_and_collects_its_records(backend, image, tmp_path):
    result = backend.run(spec(tmp_path, image))
    assert result.exit_code == 0
    assert result.termination is None

    lines = (tmp_path / "out" / "items.jsonl").read_text().splitlines()
    assert len(lines) == 10
    assert all(ItemRecord.model_validate_json(line) for line in lines)


def test_records_the_digest_of_what_actually_ran(backend, image, tmp_path):
    result = backend.run(spec(tmp_path, image))
    assert "sha256:" in result.image_digest
    assert result.backend == "docker"
    assert result.isolation == "container"


def test_a_pack_that_fails_is_a_result_not_an_error(backend, image, tmp_path):
    result = backend.run(
        spec(tmp_path, image, args=["--systems-params", "{}", "--test-params", "{}"])
    )
    assert result.exit_code != 0
    assert result.termination is None


def test_a_timeout_is_labelled_as_one(backend, tmp_path):
    result = backend.run(
        spec(
            tmp_path,
            "python:3.12-slim",
            run_id="touchstone-test-slow",
            args=["python", "-c", "import time; time.sleep(60)"],
            timeout_seconds=3,
        )
    )
    assert result.exit_code == 137
    assert result.termination == "timeout"


def test_declared_egress_is_refused_rather_than_granted(backend, image, tmp_path):
    """No host allowlist is enforceable here yet, and silently giving a pack the whole
    network because it asked for one host is how a bank finds out the hard way."""
    with pytest.raises(BackendError, match="allowlist"):
        backend.run(spec(tmp_path, image, egress=["api.openai.com"]))


def test_stdout_is_not_written_unless_asked(backend, image, tmp_path):
    backend.run(spec(tmp_path, image))
    assert list((tmp_path / "out").glob("*.stdout.log")) == []

    backend.run(spec(tmp_path, image, run_id="example-pack-1", capture_stdout=True))
    assert (tmp_path / "out" / "example-pack-1.stdout.log").is_file()


def test_reads_the_manifest_without_running_the_image(backend, image):
    manifest = backend.extract_manifest(image)
    assert manifest.name == "example_pack"
    assert {stratum.name for stratum in manifest.strata} == {"language", "difficulty"}


def test_reports_which_images_are_present(backend, image):
    assert backend.check_images([image, "touchstone/nope:0"]) == {
        image: True,
        "touchstone/nope:0": False,
    }
