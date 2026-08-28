# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Pin a plan so that a run can be repeated and an anchor can mean something.

The lock is written as canonical JSON rather than YAML so that one file carries both
properties the anchor needs: `shasum -a 256 -c PLAN.sha256` checks it with no tooling, and
the bytes are derivable from the plan data in any language. Hashing a YAML rendering would
give the first and lose the second.
"""

import hashlib
from pathlib import Path

from pydantic import ValidationError

from touchstone.backends.base import ContainerBackend
from touchstone.bundle import canonical_json, sha256_file
from touchstone.contracts import Plan
from touchstone.contracts.lock import LockedPack, PlanLock
from touchstone.errors import PlanError

LOCK_NAME = "plan.lock.json"
HASH_NAME = "PLAN.sha256"
DEFAULT_ROOT_SEED = 0


def derive_seed(root_seed: int, pack_id: str, replicate: int) -> int:
    """One root seed to a seed per pack per replicate. SHA-256 so any language agrees."""
    payload = f"{root_seed}:{pack_id}:{replicate}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def freeze(plan: Plan, backend: ContainerBackend) -> PlanLock:
    """Resolve every tag to a digest and materialise every seed."""
    root_seed = plan.seed if plan.seed is not None else DEFAULT_ROOT_SEED
    packs = []
    for pack in plan.packs:
        image = backend.resolve_digest(pack.image)
        manifest = backend.extract_manifest(image)
        if manifest is None:
            raise PlanError(
                f"{pack.id}: no manifest in {pack.image}. What the pack may reach cannot be "
                "pinned, so the plan cannot be frozen"
            )
        packs.append(
            LockedPack(
                id=pack.id,
                image=image,
                systems=pack.systems,
                params=pack.params,
                egress=manifest.network.egress,
                calibrates=manifest.calibrates,
                emits_items=manifest.emits_items,
                resources=manifest.resources,
                seeds=[derive_seed(root_seed, pack.id, n) for n in range(pack.replicates)],
            )
        )
    return PlanLock(
        plan_name=plan.plan_name,
        access_tier=plan.access_tier,
        root_seed=root_seed,
        systems=plan.systems,
        packs=packs,
    )


def lock_bytes(lock: PlanLock) -> bytes:
    """Exactly what gets hashed, and exactly what lands on disk."""
    return canonical_json(lock.model_dump()) + b"\n"


def write_lock(lock: PlanLock, directory: Path) -> tuple[Path, str]:
    """Write the lock and its hash. Returns the lock path and the hash."""
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / LOCK_NAME
    lock_path.write_bytes(lock_bytes(lock))

    digest = sha256_file(lock_path)
    # shasum's own format, so `shasum -a 256 -c PLAN.sha256` checks it with no tool of ours.
    (directory / HASH_NAME).write_text(f"{digest}  {LOCK_NAME}\n")
    return lock_path, digest


def load_lock(path: Path) -> PlanLock:
    try:
        return PlanLock.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise PlanError(f"{path}: {exc}") from exc


def recorded_hash(directory: Path) -> str:
    """The hash freeze wrote, read back out of PLAN.sha256."""
    path = directory / HASH_NAME
    if not path.is_file():
        raise PlanError(f"no {HASH_NAME} beside the lock: this plan was never frozen")
    return path.read_text().split()[0]


def check_frozen(directory: Path) -> None:
    """Raise unless the lock on disk is the one that was frozen."""
    lock_path = directory / LOCK_NAME
    if not lock_path.is_file():
        raise PlanError(f"no {LOCK_NAME} in {directory}: run touchstone freeze first")

    expected = recorded_hash(directory)
    actual = sha256_file(lock_path)
    if actual != expected:
        raise PlanError(
            f"{LOCK_NAME} has changed since it was frozen.\n"
            f"  frozen:  {expected}\n"
            f"  on disk: {actual}"
        )
