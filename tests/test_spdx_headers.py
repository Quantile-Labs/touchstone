"""Every source file carries its licence in machine readable form.

A LICENSE file at the root covers the repository. It does not travel with a file that
somebody vendors, pastes into another tree or reads out of a wheel, and an SPDX header
is the form a licence scanner in a procurement pipeline actually reads.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

COPYRIGHT = "# SPDX-FileCopyrightText: 2026 Quantile Labs"
IDENTIFIER = "# SPDX-License-Identifier: Apache-2.0"


def test_every_source_file_carries_an_spdx_header():
    missing = []
    for path in sorted(SRC.rglob("*.py")):
        head = path.read_text(encoding="utf-8").splitlines()[:2]
        if head[:2] != [COPYRIGHT, IDENTIFIER]:
            missing.append(str(path.relative_to(SRC)))
    assert not missing, "no SPDX header on the first two lines of:\n" + "\n".join(missing)


def test_the_identifier_matches_the_licence_the_package_declares():
    """A header naming one licence over a `pyproject.toml` naming another is worse than
    no header, because a scanner believes the header."""
    pyproject = (SRC.parents[0] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "Apache-2.0"' in pyproject
    assert IDENTIFIER.endswith("Apache-2.0")
