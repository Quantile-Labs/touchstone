# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Read what a bundle holds as UTF-8, whatever locale the host is set to."""

from pathlib import Path

from touchstone.errors import EncodingError


def read_text(path: Path) -> str:
    """The file as text. The default encoding is the host's, so the same bundle would
    read differently on two machines, and a file that is not text raised a traceback."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EncodingError(f"{path} is not UTF-8: {exc.reason} at byte {exc.start}") from exc


def rows(path: Path) -> list[str]:
    """The lines of a JSON lines file. Split on the newline alone, because JSON allows a
    U+2028 inside a string and `str.splitlines` breaks the row there."""
    return read_text(path).split("\n")
