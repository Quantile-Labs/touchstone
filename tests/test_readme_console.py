"""The README quotes real output, so the README is executed.

CONTEXT.md section 6: documentation that describes behaviour has a test. Three blocks are
pinned here. The `estimate` example, whose numbers are the published QL-2026-01 figures
that tests/test_estimate_credential.py exists to reproduce, and the `validate` and
`verify` lines, which print no hash and so say the same thing on any machine. The hashes
`freeze` and `bundle` quote cannot be pinned until `example_pack` is published, because
they follow an image digest that only exists on the machine that built it.
"""

import json
import re
from pathlib import Path

import yaml
from test_estimate_credential import EVIDENCED, HYBAS_ENTRIES, REAL_GAUGES
from typer.testing import CliRunner

from touchstone import bundle
from touchstone.cli import app

README = Path(__file__).resolve().parents[1] / "README.md"
BLOCK = re.compile(r"```console\n\$ touchstone estimate run-004 --by rung\n(.*?)```", re.DOTALL)
CONSOLE = re.compile(r"```console\n(.*?)```", re.DOTALL)


def _quoted_lines() -> list[str]:
    match = BLOCK.search(README.read_text())
    assert match, "the README no longer holds the estimate example this test pins"
    return [line for line in match.group(1).splitlines() if line.strip()]


def _quoted_output(command: str) -> list[str]:
    """Return the lines the README shows under a `$ command` prompt."""
    prompt = f"$ {command}"
    for block in CONSOLE.findall(README.read_text()):
        lines = block.splitlines()
        if prompt not in lines:
            continue
        output = []
        for line in lines[lines.index(prompt) + 1 :]:
            if not line.strip() or line.startswith("$ "):
                break
            output.append(line)
        return output
    raise AssertionError(f"the README no longer quotes: {prompt}")


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


def test_the_readme_validate_line_is_what_the_command_prints(monkeypatch):
    monkeypatch.chdir(README.parent)

    result = CliRunner().invoke(app, ["validate", "examples/plan.yaml"])
    assert result.exit_code == 0, result.output

    assert result.output.splitlines() == _quoted_output("touchstone validate examples/plan.yaml")


def test_the_readme_verify_line_is_what_the_command_prints(tmp_path):
    (tmp_path / "items.jsonl").write_text('{"item_id": "a"}\n')
    bundle.seal(tmp_path)

    result = CliRunner().invoke(app, ["verify", str(tmp_path)])
    assert result.exit_code == 0, result.output

    printed = result.output.replace(str(tmp_path), "./run-004").splitlines()
    assert printed == _quoted_output("touchstone verify ./run-004")


YAML_BLOCK = re.compile(r"```yaml\n(.*?)```", re.DOTALL)
EXAMPLES = README.parent / "examples"


def _yaml_blocks() -> list[dict]:
    return [yaml.safe_load(block) for block in YAML_BLOCK.findall(README.read_text())]


def test_the_readme_quotes_the_example_plan_as_it_is():
    """The plan in the README is the file, not a paraphrase of it."""
    quoted = next(block for block in _yaml_blocks() if "plan_name" in block)
    assert quoted == yaml.safe_load((EXAMPLES / "plan.yaml").read_text())


def test_the_readme_score_card_excerpt_matches_the_example_card():
    """An excerpt, so the levels and the one indicator it shows are what is checked."""
    quoted = next(block for block in _yaml_blocks() if "indicators" in block)
    card = yaml.safe_load((EXAMPLES / "scorecard.yaml").read_text())

    assert quoted["levels"] == card["levels"]
    assert quoted["tier_ceilings"]["black_box"] == card["tier_ceilings"]["black_box"]

    shown = quoted["indicators"][0]
    actual = next(item for item in card["indicators"] if item["id"] == shown["id"])
    assert shown["metric"] == actual["metric"]

    # An excerpt drops the optional prose, so every field it does show has to agree.
    for quoted_rule, real_rule in zip(shown["assessment"], actual["assessment"], strict=False):
        assert quoted_rule.items() <= real_rule.items()
