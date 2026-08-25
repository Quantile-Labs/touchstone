"""The contract every runtime implements, so the harness cannot tell them apart.

Five methods, taken from ASQI, where one workflow layer drives a Docker backend and a
Kubernetes backend without knowing which it holds. The decomposition is theirs and it is
correct. What is ours is the typing: ASQI passes seven positional arguments and returns a
bare dict, and the one method that carries evidence is the last place to lose a type.

A pack exiting non-zero is a result, not a failure: it is reported in RunResult.exit_code
and the caller decides. A backend that cannot do its job at all raises BackendError.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from touchstone.contracts import Manifest

MANIFEST_PATH = "/app/manifest.yaml"
"""Where a pack declares itself, inside the image. See docs/packs.md."""


class RunSpec(BaseModel):
    """One unit of work: a pack, at a replicate, against a system."""

    run_id: str = Field(min_length=1)
    """Unique within a run. The journal and shutdown() both key on it."""

    pack_id: str
    replicate: int = Field(default=0, ge=0)

    image: str
    """Digest-pinned by freeze. A backend resolves nothing; a tag here is a bug upstream."""

    args: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)

    output_dir: Path
    """Mounted read-write at /output. The pack writes items.jsonl and result.json here."""

    input_dir: Path | None = None
    """Mounted read-only at /input when set."""

    egress: list[str] = Field(default_factory=list)
    """Hosts the pack may reach, from manifest.network.egress. Empty means deny all."""

    capture_stdout: bool = False
    """Off by default. A pack that logs a request logs the key with it."""

    timeout_seconds: int | None = Field(default=None, gt=0)

    model_config = {"extra": "forbid"}


class RunResult(BaseModel):
    """What happened, in the form environment.json and the journal record."""

    run_id: str
    exit_code: int
    image_digest: str = Field(min_length=1)
    """What actually ran, read back from the runtime rather than from the plan."""

    backend: str
    isolation: str
    """Carried into the bundle so a reader can see the runtime was weaker than a container."""

    started_utc: str
    finished_utc: str

    stdout_path: Path | None = None
    """Set only when the spec asked for it."""

    model_config = {"extra": "forbid"}


@runtime_checkable
class ContainerBackend(Protocol):
    """A runtime that can execute a pack and hand back what it did."""

    name: str
    isolation: str
    """One word for how well this backend contains a pack, recorded in every bundle it
    produces. A subprocess runner is honest here or it is worse than useless."""

    def run(self, spec: RunSpec) -> RunResult: ...

    def shutdown(self, run_ids: list[str]) -> None:
        """Stop the named units. Called on interrupt, and safe to call on a finished run."""
        ...

    def check_images(self, images: list[str]) -> dict[str, bool]:
        """Which of these are present locally. No network."""
        ...

    def pull_images(self, images: list[str]) -> None: ...

    def extract_manifest(self, image: str, manifest_path: str = MANIFEST_PATH) -> Manifest | None:
        """Read the pack's own declaration out of the image. None if it carries none."""
        ...
