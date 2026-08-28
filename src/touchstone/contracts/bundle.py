# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What a sealed bundle records about itself.

Written by `bundle`, read by `verify`, and readable by a person with a text editor and
no copy of this tool.
"""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SHA256 = r"^[0-9a-f]{64}$"

LEDGER_DIR = "ledger"
RUNLOG_NAME = "RUNLOG.jsonl"
RUN_FINISHED = "run_finished"
"""Where a run records what it did, and the event it writes when it got to the end. Part
of the bundle layout rather than of `run`, because the thing that has to know what a
finished run looks like is the thing that refuses to seal an unfinished one."""


class FileEntry(BaseModel):
    path: str = Field(min_length=1)
    """Relative to the bundle root, forward slashes on every platform."""

    size: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256)

    model_config = {"extra": "forbid"}

    @field_validator("path")
    @classmethod
    def _stays_inside_the_bundle(cls, value: str) -> str:
        parts = PurePosixPath(value).parts
        if value.startswith("/") or ".." in parts:
            raise ValueError(f"path escapes the bundle root: {value}")
        return value


class BundleManifest(BaseModel):
    bundle_format: int = Field(default=1, ge=1)
    """Bumped when the layout changes in a way an older verify cannot read."""

    touchstone_version: str
    sealed_utc: str
    files: list[FileEntry]

    sha256: str = Field(pattern=SHA256)
    """Over the canonicalised file list alone, so it does not move when sealed_utc does.
    This is the one value a report quotes and an anchor timestamps."""

    run_ledger: Literal["complete", "absent"] = "absent"
    """Whether this bundle holds a run log that reached `run_finished`.

    `absent` is a directory assembled by hand, which is legitimate and says so here rather
    than passing for a run. There is no `incomplete`: a directory whose ledger stops before
    the end is refused, because a run that failed part way through produced files that
    hash perfectly well and mean nothing."""

    model_config = {"extra": "forbid"}
