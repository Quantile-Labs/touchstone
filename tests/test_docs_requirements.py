"""The two lists of documentation dependencies say the same thing.

`uv sync --group docs` reads pyproject.toml; Vercel reads requirements-docs.txt, because
its build image runs pip and pip does not read PEP 735 dependency groups. Two lists that
drift apart give a published site built from different versions than the one anyone
reviewed locally, and nothing else would notice.

`ruff` is exempt in one direction: it is in the dev group rather than the docs group,
because it lints this codebase and only incidentally formats signatures on the Reference
page.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-docs.txt"
PYPROJECT = ROOT / "pyproject.toml"

NAME = re.compile(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*[=<>!~]{1,2}\s*(.+)$")


def _pinned() -> dict[str, str]:
    """Distribution name to version, from the file Vercel installs."""
    found = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = NAME.match(line)
        assert match, f"unparsed requirement: {line}"
        found[match.group(1).lower()] = match.group(2)
    return found


def _grouped() -> dict[str, str]:
    """Distribution name to specifier, from the `docs` dependency group."""
    groups = tomllib.loads(PYPROJECT.read_text())["dependency-groups"]
    found = {}
    for entry in groups["docs"]:
        match = NAME.match(entry)
        assert match, f"unparsed dependency: {entry}"
        found[match.group(1).lower()] = match.group(2)
    return found


def test_every_docs_group_dependency_is_pinned_for_vercel() -> None:
    missing = sorted(set(_grouped()) - set(_pinned()))
    assert not missing, (
        f"in pyproject's docs group but not in {REQUIREMENTS.name}: {', '.join(missing)}. "
        "Vercel would build the site without them"
    )


def test_vercel_installs_nothing_the_docs_group_does_not_name() -> None:
    # ruff is the documented exception. See this module's docstring.
    extra = sorted(set(_pinned()) - set(_grouped()) - {"ruff"})
    assert not extra, (
        f"in {REQUIREMENTS.name} but not in pyproject's docs group: {', '.join(extra)}. "
        "A local build would not have them"
    )


def test_the_pins_satisfy_the_floors_the_docs_group_declares() -> None:
    pinned, grouped = _pinned(), _grouped()
    for name, floor in grouped.items():
        version = pinned[name]
        assert _parts(version) >= _parts(floor), (
            f"{name} is pinned at {version} for Vercel, below the {floor} pyproject asks for"
        )


def _parts(specifier: str) -> tuple[int, ...]:
    digits = re.findall(r"\d+", specifier)
    return tuple(int(part) for part in digits)
