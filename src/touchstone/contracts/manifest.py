"""What a pack declares about itself, read before it is run."""

from pydantic import BaseModel, Field


class SystemInput(BaseModel):
    name: str
    type: str | list[str]
    required: bool = True
    description: str | None = None


class Parameter(BaseModel):
    name: str
    type: str
    required: bool = False
    description: str | None = None


class Stratum(BaseModel):
    name: str
    values: list[str] | None = None


class Network(BaseModel):
    egress: list[str] = Field(default_factory=list)
    """Hosts this pack may reach. Empty means no egress."""


class Manifest(BaseModel):
    name: str
    version: str
    description: str | None = None
    input_systems: list[SystemInput] = Field(default_factory=list)
    input_schema: list[Parameter] = Field(default_factory=list)
    emits_items: bool = True
    """False means summary only. Such metrics carry no interval and are capped when graded."""

    locale: list[str] = Field(default_factory=list)
    """Informational. The engine never branches on it."""

    strata: list[Stratum] = Field(default_factory=list)
    network: Network = Field(default_factory=Network)

    model_config = {"extra": "forbid"}
