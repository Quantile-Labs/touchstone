"""The Protocol is only load-bearing if something is checked against it.

`runtime_checkable` verifies that the methods exist, not that their signatures match, so
these tests drive a backend through a real sequence rather than trusting isinstance alone.
Catching a wrong signature needs a type checker, and this repository does not run one yet.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from touchstone.backends import ContainerBackend, RunResult, RunSpec
from touchstone.backends.base import MANIFEST_PATH
from touchstone.contracts import Manifest

MANIFEST = Manifest(name="example_pack", version="1.0")


class FakeBackend:
    """Records what it was asked to do. Stands in for docker until docker exists."""

    name = "fake"
    isolation = "none"

    def __init__(self):
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.pulled: list[str] = []

    def run(self, spec: RunSpec) -> RunResult:
        self.started.append(spec.run_id)
        spec.output_dir.mkdir(parents=True, exist_ok=True)
        (spec.output_dir / "items.jsonl").write_text('{"item_id": "example.001"}\n')
        return RunResult(
            run_id=spec.run_id,
            exit_code=0,
            image_digest=spec.image,
            backend=self.name,
            isolation=self.isolation,
            started_utc="2026-08-25T00:00:00Z",
            finished_utc="2026-08-25T00:00:01Z",
        )

    def shutdown(self, run_ids: list[str]) -> None:
        self.stopped.extend(run_ids)

    def check_images(self, images: list[str]) -> dict[str, bool]:
        return {image: image in self.pulled for image in images}

    def pull_images(self, images: list[str]) -> None:
        self.pulled.extend(images)

    def extract_manifest(self, image: str, manifest_path: str = MANIFEST_PATH) -> Manifest | None:
        return MANIFEST


def spec(tmp_path: Path, **overrides) -> RunSpec:
    defaults = {
        "run_id": "example_pack.0",
        "pack_id": "example_pack",
        "image": "example/example_pack@sha256:" + "a" * 64,
        "output_dir": tmp_path / "out",
    }
    return RunSpec(**(defaults | overrides))


def test_a_backend_satisfies_the_protocol():
    assert isinstance(FakeBackend(), ContainerBackend)


def test_a_backend_missing_a_method_does_not():
    class Incomplete:
        name = "incomplete"
        isolation = "none"

        def run(self, spec): ...

    assert not isinstance(Incomplete(), ContainerBackend)


def test_a_backend_that_does_not_declare_its_isolation_does_not():
    class Silent:
        name = "silent"

        def run(self, spec): ...
        def shutdown(self, run_ids): ...
        def check_images(self, images): ...
        def pull_images(self, images): ...
        def extract_manifest(self, image, manifest_path=MANIFEST_PATH): ...

    assert not isinstance(Silent(), ContainerBackend)


def test_the_harness_drives_a_backend_without_knowing_which_it_is(tmp_path):
    backend: ContainerBackend = FakeBackend()
    image = "example/example_pack@sha256:" + "a" * 64

    assert backend.check_images([image]) == {image: False}
    backend.pull_images([image])
    assert backend.check_images([image]) == {image: True}
    assert backend.extract_manifest(image).name == "example_pack"

    result = backend.run(spec(tmp_path, image=image))
    assert result.exit_code == 0
    assert (tmp_path / "out" / "items.jsonl").is_file()

    backend.shutdown([result.run_id])


def test_the_result_carries_what_the_bundle_has_to_record(tmp_path):
    result = FakeBackend().run(spec(tmp_path))
    assert result.backend == "fake"
    assert result.isolation == "none"
    assert result.image_digest.startswith("example/example_pack@sha256:")


def test_stdout_is_not_captured_by_default(tmp_path):
    assert spec(tmp_path).capture_stdout is False


def test_egress_is_empty_by_default(tmp_path):
    assert spec(tmp_path).egress == []


def test_a_spec_rejects_an_unknown_field(tmp_path):
    with pytest.raises(ValidationError):
        spec(tmp_path, network_mode="host")


def test_a_spec_rejects_a_timeout_of_zero(tmp_path):
    with pytest.raises(ValidationError):
        spec(tmp_path, timeout_seconds=0)
