# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What the run actually ran on and what it took, recorded so a reader can judge the evidence.

02-DESIGN.md section 7.3: a runtime that contained the pack less well than a container
states that here. This is the access-tier logic applied to the runtime, so it has to be
machine readable rather than a sentence in a report.

The cost is here because the harness is the one party that saw every unit start and stop.
What a unit spent on the system under test only the pack can see, so the pack reports it on
each row's `cost` and the harness adds the rows up rather than taking a total from the pack.
"""

from pydantic import BaseModel, Field


class PackCost(BaseModel):
    """What one pack's units took, and what its rows say they spent."""

    pack_id: str = Field(min_length=1)
    units: int = Field(ge=0)

    wall_seconds: float = Field(ge=0.0)
    """Measured by the harness on a monotonic clock around every unit, a failed one
    included, because a unit that died after an hour of API calls still spent the hour."""

    items: int = Field(ge=0)
    items_costed: int = Field(ge=0)
    """Rows whose `cost` holds at least one figure and nothing but figures. Below `items`,
    the totals undercount by whatever the other rows spent, and nobody knows how much."""

    totals: dict[str, float] = Field(default_factory=dict)
    """Each `cost` key summed over the costed rows. Within one pack only, since two packs
    both reporting `tokens` need not be counting the same tokenizer's tokens."""

    model_config = {"extra": "forbid"}


class RunCost(BaseModel):
    """What producing the result took, per pack."""

    wall_seconds: float = Field(ge=0.0)
    """Summed over every unit of every pack. The seconds spent merging rows and writing
    files after the last unit are left out."""

    packs: list[PackCost] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class Environment(BaseModel):
    touchstone_version: str
    python: str
    platform: str

    backend: str
    isolation: str

    plan_hash: str
    image_digests: list[str] = Field(default_factory=list)
    """Every image that actually ran, read back from the runtime."""

    egress_enforced: bool | None = None
    """Across the whole run. False if any unit was granted a network it declared but the
    backend could not restrict. A claim that a pack was contained is not available then."""

    cost: RunCost | None = None
    """None in an environment.json written before `run` recorded cost, which a reader
    should take as unrecorded rather than free."""

    model_config = {"extra": "forbid"}
