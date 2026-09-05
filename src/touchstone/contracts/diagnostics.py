# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What a command says when something else is reading.

Every other contract here describes a file in a bundle. This one describes what the
commands emit under `--json`, and it is in `contracts/` for the same reason: the moment
anything parses a shape, that shape is a promise, and a promise kept in a format string
inside `cli.py` is one nobody can find.

The human output is unchanged and stays the default. A `Problem` carries the sentence that
was already printed, so the two cannot drift apart, and adds the three things prose cannot
give a machine: where the trouble is, what kind it is, and a `code` that survives somebody
improving the wording.
"""

from typing import Literal

from pydantic import BaseModel, Field

ENVELOPE_VERSION = 1
"""Bumped when a field is removed or changes meaning. Adding one is not a bump: a reader
that ignores what it does not know keeps working, and every reader should."""

Severity = Literal["error", "warning"]
"""`error` failed the command. `warning` is a finding the command still succeeded past, so
a caller that treats the two the same will fail runs that were fine."""


class Problem(BaseModel):
    """One thing wrong, or one thing worth saying, in one place."""

    code: str = Field(pattern=r"^[a-z0-9_]{1,48}$")
    """Stable, and the field to branch on. The message is written for a person and gets
    rewritten whenever it reads badly; this does not."""

    message: str = Field(min_length=1)
    """Exactly what the human output prints, so the two cannot say different things."""

    severity: Severity = "error"

    path: str | None = None
    """The file, relative to where the command was invoked. None where the problem is
    about a bundle rather than about one file in it."""

    line: int | None = None
    column: int | None = None
    """1-indexed, counting the way an editor counts. Both absent rather than zero where
    the check cannot say where it is looking: a position of 0 is a position, and a reader
    that trusts it puts a squiggle on the first character of the file."""

    subject: str | None = None
    """The pack id, indicator id or file name the problem is about, lifted out of the
    message so a caller can group by it without parsing English."""

    model_config = {"extra": "forbid", "use_attribute_docstrings": True}


class Envelope(BaseModel):
    """One command's whole answer."""

    touchstone_version: str
    envelope: int = ENVELOPE_VERSION
    command: str

    ok: bool
    """False when any problem is an error. A caller should still read the exit code, which
    says the same thing and is what a shell sees."""

    problems: list[Problem] = Field(default_factory=list)

    result: dict[str, object] = Field(default_factory=dict)
    """What the command produced, which for `estimate` and `grade` is where it wrote the
    numbers rather than the numbers themselves. `estimates.json` and `scorecard.json` are
    already contracts with their own shapes, and serialising them a second way here would
    be two answers to one question, drifting from the release they first disagree in."""

    model_config = {"extra": "forbid", "use_attribute_docstrings": True}
