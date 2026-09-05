# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What a pack declares about itself, read before it is run."""

from pydantic import BaseModel, Field


class SystemInput(BaseModel):
    name: str
    type: str | list[str]
    required: bool = True
    description: str | None = None

    model_config = {"extra": "forbid"}


class Parameter(BaseModel):
    name: str
    type: str
    required: bool = False
    description: str | None = None

    model_config = {"extra": "forbid"}


class Stratum(BaseModel):
    name: str
    values: list[str] | None = None

    model_config = {"extra": "forbid"}


class Network(BaseModel):
    egress: list[str] = Field(default_factory=list)
    """Hosts this pack may reach. Empty means no egress."""

    model_config = {"extra": "forbid"}


class Resources(BaseModel):
    """The blast radius of one pack, declared by the pack.

    ASQI caps memory at 2g and CPU at two cores, and does it as a global default a pack
    cannot express a need for: a pack that genuinely wants 8g has nowhere to say so, and
    the operator raises the cap for every pack at once or not at all. Declaring it here
    makes the ceiling per pack, reviewable in the frozen plan, and the defaults below match
    ASQI's so a pack that says nothing behaves the same under both.
    """

    memory_mb: int = Field(default=2048, ge=64)
    """Swap is pinned to this same figure at run time. A memory cap that leaves swap open
    is a cap the container walks straight through."""

    cpus: float = Field(default=2.0, gt=0)
    pids: int = Field(default=512, ge=16)
    """Processes. ASQI caps neither, so a pack that forks in a loop takes the host down
    while staying inside its memory limit."""

    model_config = {"extra": "forbid"}


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
    resources: Resources = Field(default_factory=Resources)

    calibrates: str | None = None
    """Which outcome the `confidence` on an item record is a claim about.

    An item carries one confidence, so it is a claim about one outcome, and only the pack
    knows which. Declared here rather than passed at analysis time because it is a fact
    about the pack's schema, not a choice a reader makes. Binning a confidence against an
    unrelated boolean gives an ECE that reads as authoritative and means nothing."""

    model_config = {"extra": "forbid"}
