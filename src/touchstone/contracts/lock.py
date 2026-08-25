"""A plan with nothing left to interpret. What freeze produces and run consumes."""

from pydantic import BaseModel, Field

from touchstone.contracts.plan import System

DIGEST_PINNED = r"^[^\s]+@sha256:[0-9a-f]{64}$"


class LockedPack(BaseModel):
    id: str
    image: str = Field(pattern=DIGEST_PINNED)
    """Bytes, not a label. A tag here means the lock was hand edited."""

    systems: dict[str, str] = Field(default_factory=dict)
    params: dict[str, object] = Field(default_factory=dict)

    seeds: list[int]
    """One per replicate, derived from the root seed and recorded so a rerun matches."""

    model_config = {"extra": "forbid"}


class PlanLock(BaseModel):
    """Plan content only. No timestamp and no tool version, so freezing the same plan
    twice produces the same bytes and therefore the same hash. When it was frozen is an
    event, and events belong in the ledger."""

    lock_format: int = Field(default=1, ge=1)
    plan_name: str
    access_tier: str
    root_seed: int
    systems: dict[str, System]
    packs: list[LockedPack]

    model_config = {"extra": "forbid"}
