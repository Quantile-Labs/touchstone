"""The README quotes real output, so the README is executed.

CONTEXT.md section 6: documentation that describes behaviour has a test. The README block
this checks is the `estimate` example, whose numbers are the published QL-2026-01 figures
that tests/test_estimate_credential.py exists to reproduce. Without this, changing a
message string drifts the README silently.
"""

import json
import re
from pathlib import Path

from test_estimate_credential import EVIDENCED, HYBAS_ENTRIES, REAL_GAUGES
from typer.testing import CliRunner

from touchstone.cli import app

README = Path(__file__).resolve().parents[1] / "README.md"
BLOCK = re.compile(r"```console\n\$ touchstone estimate run-004 --by rung\n(.*?)```", re.DOTALL)


def _quoted_lines() -> list[str]:
    match = BLOCK.search(README.read_text())
    assert match, "the README no longer holds the estimate example this test pins"
    return [line for line in match.group(1).splitlines() if line.strip()]


def test_the_readme_estimate_example_is_what_the_command_prints(tmp_path):
    records = [
        {
            "item_id": f"gauge.{index:04d}",
            "stratum": {"rung": "real_gauge"},
            "outcome": {"evidenced": index < EVIDENCED},
        }
        for index in range(REAL_GAUGES)
    ] + [
        {
            "item_id": f"hybas.{index:04d}",
            "stratum": {"rung": "hybas_entry"},
            "outcome": {"evidenced": False},
        }
        for index in range(HYBAS_ENTRIES)
    ]
    (tmp_path / "items.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    )

    result = CliRunner().invoke(app, ["estimate", str(tmp_path), "--by", "rung"])
    assert result.exit_code == 0, result.output

    printed = [line.replace(str(tmp_path), "run-004") for line in result.output.splitlines()]
    assert [line for line in printed if line.strip()] == _quoted_lines()
