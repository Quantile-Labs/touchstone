"""`__version__` is what lands in a bundle, so it has to be the version that was released."""

import re
import tomllib
from pathlib import Path

from touchstone import __version__

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_version_matches_pyproject() -> None:
    declared = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert __version__ == declared, (
        f"__version__ is {__version__} and pyproject.toml says {declared}. "
        "Every bundle, estimate and score card stamps __version__, so a release that "
        "bumps only pyproject.toml seals artefacts naming a version nobody published"
    )


def test_version_is_a_release_number() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
