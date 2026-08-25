"""A plan with nothing left to interpret. What freeze produces and run consumes."""

from pydantic import BaseModel, Field

from touchstone.contracts.manifest import Resources
from touchstone.contracts.plan import System

DIGEST_PINNED = r"^[^\s]+@sha256:[0-9a-f]{64}$"


class LockedPack(BaseModel):
    id: str
    image: str = Field(pattern=DIGEST_PINNED)
    """Bytes, not a label. A tag here means the lock was hand edited."""

    systems: dict[str, str] = Field(default_factory=dict)
    params: dict[str, object] = Field(default_factory=dict)

    egress: list[str] = Field(default_factory=list)
    """Hosts this pack declared, read from its manifest at freeze time and pinned here so
    a security review reads the frozen plan rather than the image. Empty means no network."""

    calibrates: str | None = None
    """The outcome this pack's `confidence` is a claim about, read from its manifest at
    freeze time and pinned here, so what was calibrated is part of the frozen plan rather
    than a flag somebody typed."""

    emits_items: bool = True
    """False means the pack reported summaries and no observations. Read from its manifest
    at freeze time, because a sealed bundle otherwise has no way to tell a rate computed
    from items apart from one a container asserted, and `grade` caps the second. See
    02-DESIGN.md section 3.4."""

    resources: Resources = Field(default_factory=Resources)
    """What the pack declared it needs, read from its manifest at freeze time. Pinned here
    for the same reason as `egress`: a reviewer reads the ceiling off the frozen plan
    rather than off an image they would have to pull."""

    seeds: list[int]
    """One per replicate, derived from the root seed and recorded so a rerun matches."""

    model_config = {"extra": "forbid"}


class PlanLock(BaseModel):
    """Plan content only. No timestamp and no tool version, so freezing the same plan
    twice produces the same bytes and therefore the same hash. When it was frozen is an
    event, and events belong in the ledger."""

    lock_format: int = Field(default=4, ge=1)
    """2 added `calibrates`, 3 added `emits_items`, 4 added `resources`. A format bump
    changes the bytes and therefore the hash of an unchanged plan, which is the point."""

    plan_name: str
    access_tier: str
    root_seed: int
    systems: dict[str, System]
    packs: list[LockedPack]

    model_config = {"extra": "forbid"}
