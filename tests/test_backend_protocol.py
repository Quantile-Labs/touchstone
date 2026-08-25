"""The Protocol in backends/base.py is only a contract if something checks it.

runtime_checkable was measured and it is not enough: isinstance passes a backend whose
method signatures are wrong, and only a missing method or a missing isolation attribute
fails it. These tests pin both halves, so nobody removes the type checker believing
isinstance already covers this.
"""

import shutil
import subprocess
import sys

import pytest

from touchstone.backends.base import ContainerBackend

WRONG_SIGNATURE = """
from touchstone.backends.base import ContainerBackend, RunResult
from touchstone.contracts import Manifest


class WrongSignature:
    name = "wrong"
    isolation = "none"

    def run(self, spec: str) -> RunResult: ...
    def shutdown(self, run_ids: list[str]) -> None: ...
    def resolve_digest(self, image: str) -> str: ...
    def check_images(self, images: list[str]) -> dict[str, bool]: ...
    def pull_images(self, images: list[str]) -> None: ...
    def extract_manifest(self, image: str, manifest_path: str = "") -> Manifest | None: ...


backend: ContainerBackend = WrongSignature()
"""


class WrongSignature:
    """run() takes a str where the Protocol says RunSpec. Everything else matches."""

    name = "wrong"
    isolation = "none"

    def run(self, spec: str) -> None: ...
    def shutdown(self, run_ids: list[str]) -> None: ...
    def resolve_digest(self, image: str) -> str: ...
    def check_images(self, images: list[str]) -> dict[str, bool]: ...
    def pull_images(self, images: list[str]) -> None: ...
    def extract_manifest(self, image: str, manifest_path: str = "") -> None: ...


def test_isinstance_does_not_check_signatures():
    """Why mypy is in CI. If this ever fails, isinstance grew teeth and the note above
    needs rewriting, not the test."""
    assert isinstance(WrongSignature(), ContainerBackend)


def test_mypy_rejects_a_backend_with_the_wrong_signature(tmp_path):
    if shutil.which("mypy") is None and not _mypy_importable():
        pytest.skip("mypy is not installed")

    source = tmp_path / "wrong_backend.py"
    source.write_text(WRONG_SIGNATURE)

    done = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(source)],
        capture_output=True,
        text=True,
    )

    assert done.returncode != 0, "mypy accepted a backend that does not implement the Protocol"
    assert "assignment" in done.stdout, done.stdout


def _mypy_importable() -> bool:
    try:
        import mypy  # noqa: F401
    except ImportError:
        return False
    return True
