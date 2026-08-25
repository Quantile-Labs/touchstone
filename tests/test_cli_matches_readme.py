"""Every command in the README pipeline table exists in the CLI.

Documentation that drifts from the code is how a contract stops being one.
"""

import re
from pathlib import Path

from typer.main import get_command

from touchstone.cli import app

README = Path(__file__).resolve().parents[1] / "README.md"


def documented_commands() -> set[str]:
    table = README.read_text().split("## The pipeline", 1)[1].split("##", 1)[0]
    return set(re.findall(r"^\| `([a-z]+)` \|", table, re.MULTILINE))


def test_every_documented_command_exists():
    actual = set(get_command(app).commands)
    missing = documented_commands() - actual
    assert not missing, f"documented but not implemented: {sorted(missing)}"
