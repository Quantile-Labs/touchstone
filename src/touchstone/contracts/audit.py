# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What a person assessed, for the indicators no bundle can answer on its own.

Two of the DQI 0.1 indicators are not computed. Whether someone subject to an adverse
decision can obtain the reason and challenge it, and whether the artefact evaluated is the
artefact deployed, are both read off an organisation rather than off `items.jsonl`. The
engine still refuses to grade them itself: it takes a level an assessor recorded, checks it
is on the ladder the score card declares, and applies the same access tier ceiling as
every computed indicator, so a human judgment cannot claim more than the access allowed.

Every response carries its evidence for the same reason every rate carries its denominator.
A level with nothing behind it is an assertion, and this file travels into the bundle.
"""

from pydantic import BaseModel, Field

AUDIT_NAME = "audit.yaml"
"""What the responses are called inside a bundle. `grade` copies them in, because a grade
that cannot be recomputed from the bundle is not evidence."""


class AuditResponse(BaseModel):
    """One indicator, as a person assessed it."""

    level: str = Field(min_length=1)
    """A level from the score card's own ladder. One that is not on it is an error rather
    than a rounding, because the assessor and the card would then disagree about the
    vocabulary and the grade would be meaningless."""

    evidence: str = Field(min_length=1)
    """What was examined. Required: an audit level with nothing behind it is an opinion,
    and this is the field a reviewer argues with."""

    model_config = {"extra": "forbid", "use_attribute_docstrings": True}


class AuditResponses(BaseModel):
    """The file an assessor fills in, keyed by indicator id."""

    audit_name: str = Field(min_length=1)
    assessor: str = Field(min_length=1)
    """Who assessed it. Named, because an audit outcome is a person's judgment and a
    judgment with no author cannot be questioned."""

    assessed_utc: str = Field(min_length=1)

    responses: dict[str, AuditResponse] = Field(min_length=1)
    """Indicator id to what was found. An id the score card does not declare is an error:
    it is either a typo or an audit of a different card, and both produce a bundle whose
    grades came from somewhere nobody can identify."""

    model_config = {"extra": "forbid", "use_attribute_docstrings": True}
