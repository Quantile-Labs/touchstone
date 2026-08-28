# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What the run actually ran on, recorded so a reader can judge the evidence.

02-DESIGN.md section 7.3: a runtime that contained the pack less well than a container
states that here. This is the access-tier logic applied to the runtime, so it has to be
machine readable rather than a sentence in a report.
"""

from pydantic import BaseModel, Field


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

    model_config = {"extra": "forbid"}
