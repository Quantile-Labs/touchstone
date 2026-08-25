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
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import yaml

from touchstone.backends import egress
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

    def _cli(self, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
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

    def resolve_digest(self, image: str) -> str:
        """What actually ran. A locally built image has no RepoDigests, so fall back to
        the image id, which is still a content hash of exactly what executed."""
        fmt = "{{json .RepoDigests}}"
        digests: list[str] = json.loads(self._require("image", "inspect", "--format", fmt, image))
        if digests:
            return digests[0]
        return self._require("image", "inspect", "--format", "{{.Id}}", image)

    def run(self, spec: RunSpec) -> RunResult:
        """One unit of work, contained. Enforces a declared allowlist unless told not to."""
        if not spec.egress:
            return self._run(spec, network="none", egress_enforced=None)

        if spec.allow_unenforced_egress:
            # The override means the whole network, not the hosts the pack asked for. It
            # is a downgrade of something this backend can now do, so it is only ever
            # taken because the caller asked for it in as many words.
            return self._run(spec, network="bridge", egress_enforced=False)

        with self._contained(spec) as network:
            return self._run(spec, network=network, egress_enforced=True)

    @contextmanager
    def _contained(self, spec: RunSpec) -> Iterator[str]:
        """A network with no route out, and a proxy on it that is the only way through.

        Anything that goes wrong here raises. Falling back to an open network would turn a
        broken control into a silent one, which is the failure mode 01-ASQI-TEARDOWN.md
        section 4 defect 1 is about.
        """
        rejected = egress.check_hosts(spec.egress)
        if rejected:
            raise BackendError(
                f"{spec.pack_id} declares egress to {', '.join(rejected)}, which is not a "
                "hostname. The allowlist is written into a proxy configuration, so a host "
                "carrying anything but a name is refused rather than escaped"
            )

        network = f"{spec.run_id}-net"
        proxy = f"{spec.run_id}-proxy"
        self._require("network", "create", "--internal", network)
        try:
            self._require(
                "run",
                "-d",
                "--name",
                proxy,
                "--network",
                network,
                "--network-alias",
                egress.PROXY_ALIAS,
                "--entrypoint",
                "sh",
                egress.PROXY_IMAGE,
                "-c",
                egress.start_command(egress.squid_config(spec.egress)),
            )
            # The proxy needs a way out that the pack does not have. Attaching it to the
            # default bridge after the fact is what makes the two networks asymmetric.
            self._require("network", "connect", "bridge", proxy)
            self._await_proxy(proxy, spec.pack_id)
            yield network
        finally:
            # Stop before reading. Squid buffers its access log and the image tails that
            # file to stdout, so killing the container outright loses the last requests,
            # which are the ones a reviewer most wants to see.
            self._cli("stop", "--timeout", "5", proxy)
            self._write_access_log(proxy, spec)
            self._cli("rm", "--force", proxy)
            self._cli("network", "rm", network)

    def _await_proxy(self, proxy: str, pack_id: str, seconds: int = 30) -> None:
        for _ in range(seconds * 2):
            logs = self._cli("logs", proxy)
            if egress.READY in logs.stdout or egress.READY in logs.stderr:
                return
            if (
                self._cli("inspect", "--format", "{{.State.Running}}", proxy).stdout.strip()
                != "true"
            ):
                raise BackendError(
                    f"{pack_id}: the egress proxy exited before it accepted connections. "
                    f"{logs.stderr.strip() or logs.stdout.strip()}"
                )
            time.sleep(0.5)
        raise BackendError(f"{pack_id}: the egress proxy did not start within {seconds}s")

    def _write_access_log(self, proxy: str, spec: RunSpec) -> None:
        """Every request the pack made and what the proxy did about it, into the bundle.

        The claim is that the pack reached the hosts it declared and nothing else. This is
        the line by line evidence for it, and a denial in here is a finding rather than an
        error: it says the pack tried.
        """
        logs = self._cli("logs", proxy)
        entries = [line for line in logs.stdout.splitlines() if "CONNECT" in line or "TCP_" in line]
        if not entries:
            return
        path = spec.output_dir / f"{spec.run_id}.egress.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(entries) + "\n")

    def _run(self, spec: RunSpec, network: str, egress_enforced: bool | None) -> RunResult:
        spec.output_dir.mkdir(parents=True, exist_ok=True)
        args = [
            "run",
            "--rm",
            "--name",
            spec.run_id,
            "--network",
            network,
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
        if egress_enforced:
            # Written after the pack's own environment, so a pack cannot point itself at a
            # different proxy. It could ignore these and still reach nothing: the network
            # is the control and this is the courtesy.
            for key, value in egress.proxy_env().items():
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
            image_digest=self.resolve_digest(spec.image),
            backend=self.name,
            isolation=self.isolation,
            started_utc=started,
            finished_utc=_now(),
            stdout_path=stdout_path,
            termination=termination,
            egress_enforced=egress_enforced,
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


def _untar_one(payload: bytes) -> dict[str, Any]:
    """Read the single file docker cp wrote into its tar stream."""
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        member = archive.next()
        if member is None:
            raise BackendError("empty archive from docker cp")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise BackendError(f"{member.name} is not a regular file")
        loaded: dict[str, Any] = yaml.safe_load(extracted.read())
        return loaded
