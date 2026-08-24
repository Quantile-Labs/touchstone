"""What the analyst writes, and what freeze turns into an anchor."""

from pydantic import BaseModel, Field


class PackRef(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    image: str
    systems: dict[str, str] = Field(default_factory=dict)
    params: dict[str, object] = Field(default_factory=dict)
    replicates: int = Field(default=1, ge=1)


class System(BaseModel):
    type: str
    params: dict[str, object] = Field(default_factory=dict)


class Plan(BaseModel):
    plan_name: str
    access_tier: str
    """No claim in the report may exceed the tier declared here."""

    seed: int | None = None
    systems: dict[str, System]
    packs: list[PackRef]

    model_config = {"extra": "forbid"}
