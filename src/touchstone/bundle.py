"""Read and verify an evidence bundle."""

import hashlib
import json
from pathlib import Path

from touchstone.errors import BundleError

MANIFEST_NAME = "MANIFEST.json"
CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify(bundle_dir: Path) -> list[str]:
    """Re-check every file against MANIFEST.json. Returns the list of failures."""
    manifest_path = bundle_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise BundleError(f"no {MANIFEST_NAME} in {bundle_dir}")

    try:
        entries = json.loads(manifest_path.read_text())["files"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise BundleError(f"{MANIFEST_NAME} is malformed: {exc}") from exc

    failures = []
    recorded = set()

    for entry in entries:
        name = entry["path"]
        recorded.add(name)
        target = bundle_dir / name
        if not target.is_file():
            failures.append(f"missing: {name}")
            continue
        actual = sha256_file(target)
        if actual != entry["sha256"]:
            failures.append(f"hash mismatch: {name}")

    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        name = str(path.relative_to(bundle_dir))
        if name != MANIFEST_NAME and name not in recorded:
            failures.append(f"not recorded: {name}")

    return failures
