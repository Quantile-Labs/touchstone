"""Seal an evidence bundle and re-check a sealed one."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from touchstone import __version__
from touchstone.contracts.bundle import BundleManifest, FileEntry
from touchstone.errors import BundleError

MANIFEST_NAME = "MANIFEST.json"
CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    """Serialise to the byte form that gets hashed. Sorted keys, no insignificant space."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def bundle_hash(files: list[FileEntry]) -> str:
    """Hash the file list. Independent of how MANIFEST.json itself is formatted."""
    return hashlib.sha256(canonical_json([entry.model_dump() for entry in files])).hexdigest()


def _walk(bundle_dir: Path) -> list[FileEntry]:
    entries = []
    for path in sorted(bundle_dir.rglob("*")):
        name = path.relative_to(bundle_dir).as_posix()
        if path.is_symlink():
            raise BundleError(f"symlink in bundle: {name}. Evidence has to be self-contained")
        if not path.is_file() or name == MANIFEST_NAME:
            continue
        entries.append(FileEntry(path=name, size=path.stat().st_size, sha256=sha256_file(path)))
    return entries


def seal(bundle_dir: Path) -> BundleManifest:
    """Hash every file under the directory and write MANIFEST.json. Returns the manifest."""
    if not bundle_dir.is_dir():
        raise BundleError(f"not a directory: {bundle_dir}")
    if (bundle_dir / MANIFEST_NAME).exists():
        raise BundleError(f"already sealed: remove {MANIFEST_NAME} to seal {bundle_dir} again")

    files = _walk(bundle_dir)
    if not files:
        raise BundleError(f"nothing to seal in {bundle_dir}")

    manifest = BundleManifest(
        touchstone_version=__version__,
        sealed_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        files=files,
        sha256=bundle_hash(files),
    )
    # Indented on purpose. The bundle has to be readable years from now by someone
    # holding a text editor and nothing else.
    (bundle_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n"
    )
    return manifest


def load_manifest(bundle_dir: Path) -> BundleManifest:
    path = bundle_dir / MANIFEST_NAME
    if not path.is_file():
        raise BundleError(f"no {MANIFEST_NAME} in {bundle_dir}")
    try:
        return BundleManifest.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise BundleError(f"{MANIFEST_NAME} is malformed: {exc}") from exc


def verify(bundle_dir: Path) -> list[str]:
    """Re-check every file against MANIFEST.json. Returns the list of failures."""
    manifest = load_manifest(bundle_dir)
    failures = []

    if bundle_hash(manifest.files) != manifest.sha256:
        failures.append("bundle hash does not match the recorded file list")

    for entry in manifest.files:
        target = bundle_dir / entry.path
        if not target.is_file():
            failures.append(f"missing: {entry.path}")
        elif sha256_file(target) != entry.sha256:
            failures.append(f"hash mismatch: {entry.path}")

    recorded = {entry.path for entry in manifest.files}
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(bundle_dir).as_posix()
        if name != MANIFEST_NAME and name not in recorded:
            failures.append(f"not recorded: {name}")

    return failures
