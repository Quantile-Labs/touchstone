"""Run a pack in a container, through the docker CLI.

The CLI rather than the docker SDK, which pulls requests, urllib3 and certifi. An HTTP
stack and a CA bundle in the dependency closure of `touchstone verify` is the wrong thing
to hand a regulator who was told the command never touches the network. Swapping the
binary also makes podman and nerdctl work.
"""

import io
import json
import os
import subprocess
import tarfile
from datetime import UTC, datetime

import yaml

from touchstone.backends.base import MANIFEST_PATH, ContainerBackend, RunResult, RunSpec
from touchstone.contracts import Manifest
from touchstone.errors import BackendError

TIMEOUT_EXIT = 137
"""What docker reports for a killed container, and what ASQI reports for a timeout."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class DockerBackend(ContainerBackend):
    """Containers, one per unit of work."""

    name = "docker"
    isolation = "container"

    def __init__(self, binary: str = "docker"):
        self.binary = binary

    def _cli(self, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [self.binary, *args], capture_output=True, text=True, timeout=timeout
            )
        except FileNotFoundError as exc:
            raise BackendError(f"{self.binary} is not on PATH") from exc

    def _require(self, *args: str) -> str:
        done = self._cli(*args)
        if done.returncode != 0:
            raise BackendError(f"{self.binary} {' '.join(args)}: {done.stderr.strip()}")
        return done.stdout.strip()

    def _digest(self, image: str) -> str:
        """What actually ran. A locally built image has no RepoDigests, so fall back to
        the image id, which is still a content hash of exactly what executed."""
        fmt = "{{json .RepoDigests}}"
        digests = json.loads(self._require("image", "inspect", "--format", fmt, image))
        if digests:
            return digests[0]
        return self._require("image", "inspect", "--format", "{{.Id}}", image)

    def run(self, spec: RunSpec) -> RunResult:
        if spec.egress:
            raise BackendError(
                f"{spec.pack_id} declares egress to {', '.join(spec.egress)} and this backend "
                "cannot enforce a host allowlist. Refusing rather than granting full network"
            )

        spec.output_dir.mkdir(parents=True, exist_ok=True)
        args = [
            "run",
            "--rm",
            "--name",
            spec.run_id,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            # As the caller, not root and not the image's USER. A bind mount on Linux keeps
            # host ownership, so anything else cannot write to /output, and root would leave
            # the analyst files they cannot delete. Docker Desktop maps uids and hides both.
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--volume",
            f"{spec.output_dir.resolve()}:/output",
        ]
        if spec.input_dir is not None:
            args += ["--volume", f"{spec.input_dir.resolve()}:/input:ro"]
        for key, value in spec.environment.items():
            args += ["--env", f"{key}={value}"]
        args += [spec.image, *spec.args]

        started = _now()
        try:
            done = self._cli(*args, timeout=spec.timeout_seconds)
            exit_code, termination = done.returncode, None
            stdout = done.stdout
        except subprocess.TimeoutExpired:
            self.shutdown([spec.run_id])
            exit_code, termination, stdout = TIMEOUT_EXIT, "timeout", ""

        stdout_path = None
        if spec.capture_stdout:
            stdout_path = spec.output_dir / f"{spec.run_id}.stdout.log"
            stdout_path.write_text(stdout)

        return RunResult(
            run_id=spec.run_id,
            exit_code=exit_code,
            image_digest=self._digest(spec.image),
            backend=self.name,
            isolation=self.isolation,
            started_utc=started,
            finished_utc=_now(),
            stdout_path=stdout_path,
            termination=termination,
            native_id=spec.run_id,
        )

    def shutdown(self, run_ids: list[str]) -> None:
        for run_id in run_ids:
            self._cli("rm", "--force", run_id)

    def check_images(self, images: list[str]) -> dict[str, bool]:
        return {image: self._cli("image", "inspect", image).returncode == 0 for image in images}

    def pull_images(self, images: list[str]) -> None:
        for image in images:
            self._require("pull", image)

    def extract_manifest(self, image: str, manifest_path: str = MANIFEST_PATH) -> Manifest | None:
        """Copy the declaration out without running anything in the image."""
        container = self._require("create", image)
        try:
            # docker cp writes a tar to stdout, so this one call cannot be text mode.
            done = subprocess.run(
                [self.binary, "cp", f"{container}:{manifest_path}", "-"], capture_output=True
            )
            if done.returncode != 0:
                return None
            return Manifest.model_validate(_untar_one(done.stdout))
        finally:
            self._cli("rm", "--force", container)


def _untar_one(payload: bytes) -> dict:
    """Read the single file docker cp wrote into its tar stream."""
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        member = archive.next()
        if member is None:
            raise BackendError("empty archive from docker cp")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise BackendError(f"{member.name} is not a regular file")
        return yaml.safe_load(extracted.read())
