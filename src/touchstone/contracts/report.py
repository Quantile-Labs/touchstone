# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What a conformance statement says about a bundle.

The findings are computed from the bundle and nothing else. A reader who disagrees with a
line can open the file it names and check it, which is the only reason to publish a
statement of conformance at all.
"""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["met", "not met", "not applicable"]
"""Three, and no fourth. A partial credit column is where a conformance report stops being
readable, because every line becomes partial and the reader has to grade the grader."""


class Finding(BaseModel):
    """One practice item, and what the bundle holds against it."""

    code: str = Field(pattern=r"^[a-z0-9_]{1,48}$")
    """Stable. The practice reference moves when a draft is revised and this does not."""

    practice: str | None = None
    """The reference in the source, where the item has one. None for the four this project
    added, which the survey's summary of the practices missed."""

    requirement: str = Field(min_length=1)
    """What is being asked, in one line."""

    status: Status
    detail: str = Field(min_length=1)
    """What the bundle actually holds. Written to be argued with, so it names figures and
    files rather than restating the requirement in the past tense."""

    evidence: list[str] = Field(default_factory=list)
    """The files the finding was read from, relative to the bundle."""

    model_config = {"extra": "forbid", "use_attribute_docstrings": True}


class Report(BaseModel):
    """A conformance statement over one bundle."""

    touchstone_version: str
    profile: str
    """Which practice set was applied."""

    source: str
    """The document the practice references point into, with its identifier."""

    bundle: str
    bundle_sha256: str | None = None
    plan_sha256: str | None = None
    sealed_utc: str | None = None
    access_tier: str | None = None

    verified: bool | None = None
    """Whether the bundle's own hashes still check out at the moment the report was made.
    None where it is not sealed yet, which is a different statement from failing."""

    findings: list[Finding] = Field(default_factory=list)

    model_config = {"extra": "forbid", "use_attribute_docstrings": True}

    @property
    def met(self) -> int:
        return sum(1 for finding in self.findings if finding.status == "met")

    @property
    def unmet(self) -> int:
        return sum(1 for finding in self.findings if finding.status == "not met")
