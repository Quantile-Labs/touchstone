"""`--json` on the commands that check something, read the way a machine reads it.

Every assertion here is on a `code`, a position or a count, and never on a sentence. That
is the point of the flag: the prose is written for a person and gets rewritten whenever it
reads badly, so anything that parses it breaks on a wording change nobody thought was a
change. The sentences are still carried in `message` and are still tested where they are
the thing under test, in `test_readme_console.py` and the command tests beside it.
"""

import json
import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from touchstone.cli import app
from touchstone.contracts.diagnostics import ENVELOPE_VERSION

runner = CliRunner()

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "run-001"
EXAMPLE_PLAN = ROOT / "examples" / "plan.yaml"
PACKS = ROOT / "packs"


def envelope(*args: str) -> tuple[dict, int]:
    """Run the CLI and parse stdout whole. A parse failure here is the finding: anything
    printed beside the envelope makes the flag useless to the caller it exists for."""
    result = runner.invoke(app, list(args))
    return json.loads(result.stdout), result.exit_code


def codes(payload: dict) -> list[str]:
    return [problem["code"] for problem in payload["problems"]]


def test_the_envelope_says_which_version_wrote_it():
    payload, status = envelope("validate", str(EXAMPLE_PLAN), "-m", str(PACKS), "--json")

    assert status == 0
    assert payload["envelope"] == ENVELOPE_VERSION
    assert payload["touchstone_version"]
    assert payload["command"] == "validate"
    assert payload["ok"] is True
    assert payload["problems"] == []
    assert payload["result"]["packs"] == 1


def test_a_parameter_the_pack_does_not_accept_carries_a_code_and_a_position(tmp_path):
    """The one the roadmap entry was written for. A caller branches on `parameter_unknown`
    and puts a squiggle under the key, without reading a word of the message."""
    plan = yaml.safe_load(EXAMPLE_PLAN.read_text())
    plan["packs"][0]["params"]["nope"] = 1
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(plan, sort_keys=False))

    payload, status = envelope("validate", str(path), "-m", str(PACKS), "--json")

    assert status == 1
    assert payload["ok"] is False
    assert codes(payload) == ["parameter_unknown"]

    problem = payload["problems"][0]
    assert problem["path"] == str(path)
    assert problem["subject"] == "example_pack"
    assert problem["severity"] == "error"

    written = path.read_text().splitlines()
    assert written[problem["line"] - 1].strip().startswith("nope:")
    assert written[problem["line"] - 1][problem["column"] - 1 :].startswith("nope")


def test_a_pack_with_no_manifest_points_at_the_pack_that_names_it(tmp_path):
    plan = yaml.safe_load(EXAMPLE_PLAN.read_text())
    plan["packs"][0]["id"] = "ghost_pack"
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(plan, sort_keys=False))

    payload, status = envelope("validate", str(path), "-m", str(PACKS), "--json")

    assert status == 1
    assert codes(payload) == ["pack_manifest_missing"]
    assert payload["problems"][0]["subject"] == "ghost_pack"
    written = path.read_text().splitlines()
    assert "ghost_pack" in written[payload["problems"][0]["line"] - 1]


def test_a_plan_that_will_not_load_is_one_problem_and_not_a_traceback(tmp_path):
    path = tmp_path / "plan.yaml"
    path.write_text("plan_name: 3\naccess_tier: [\n")

    payload, status = envelope("validate", str(path), "-m", str(PACKS), "--json")

    assert status == 1
    assert codes(payload) == ["plan_error"]
    assert payload["problems"][0]["line"] is None
    assert payload["problems"][0]["column"] is None


def test_a_position_is_absent_rather_than_zero(tmp_path):
    """A caller that reads 0 as a line puts the mark on the first character of the file.
    Absent is the only honest answer where a check cannot say where it is looking, and a
    hash is a fact about a whole file rather than about a line in it."""
    bundle_dir = tmp_path / "run"
    shutil.copytree(GOLDEN, bundle_dir)
    (bundle_dir / "items.jsonl").write_text("tampered\n")
    (bundle_dir / "extra.txt").write_text("added later\n")

    payload, status = envelope("verify", str(bundle_dir), "--json")

    assert status == 1
    assert len(payload["problems"]) == 2
    for problem in payload["problems"]:
        assert problem["line"] is None
        assert problem["column"] is None
        assert problem["path"] is not None


def test_verify_names_the_file_that_moved(tmp_path):
    bundle_dir = tmp_path / "run"
    shutil.copytree(GOLDEN, bundle_dir)
    (bundle_dir / "items.jsonl").write_text("tampered\n")

    payload, status = envelope("verify", str(bundle_dir), "--json")

    assert status == 1
    assert payload["ok"] is False
    assert "file_hash_mismatch" in codes(payload)
    moved = next(p for p in payload["problems"] if p["code"] == "file_hash_mismatch")
    assert moved["subject"] == "items.jsonl"
    assert moved["path"] == str(bundle_dir / "items.jsonl")


def test_verify_on_a_directory_that_is_not_a_bundle_is_a_bundle_error(tmp_path):
    payload, status = envelope("verify", str(tmp_path), "--json")

    assert status == 1
    assert codes(payload) == ["bundle_error"]


def test_estimate_points_at_what_it_wrote_rather_than_repeating_it(tmp_path):
    """`estimates.json` is already a contract. Serialising the same numbers into the
    envelope would be a second shape for them, and the two would disagree eventually."""
    run_dir = tmp_path / "run"
    shutil.copytree(GOLDEN, run_dir)
    (run_dir / "MANIFEST.json").unlink()

    payload, status = envelope("estimate", str(run_dir), "--json")

    assert status == 0
    assert payload["ok"] is True
    assert payload["result"]["path"] == str(run_dir / "estimates.json")
    assert payload["result"]["items"] > 0
    assert set(payload["result"]) == {"path", "estimates", "items", "packs"}
    assert isinstance(payload["result"]["estimates"], int), "a count, not the estimates"


def test_an_indeterminate_grade_is_a_warning_and_the_command_still_succeeded(graded):
    """A caller that treats every problem as a failure fails a run that measured what it
    set out to measure and reported honestly that the interval spans a boundary."""
    run_dir, card = graded

    payload, status = envelope("grade", str(run_dir), "--score-card", str(card), "--json")

    assert status == 0
    assert payload["ok"] is True
    assert codes(payload) == ["indeterminate"]

    warning = payload["problems"][0]
    assert warning["severity"] == "warning"
    assert warning["subject"] == "headline_accuracy"
    assert card.read_text().splitlines()[warning["line"] - 1].strip().startswith("- id:")


def test_a_score_card_naming_a_metric_the_bundle_lacks_fails_with_a_code(graded):
    run_dir, card = graded
    card.write_text(card.read_text().replace("name: correct", "name: never_computed"))

    payload, status = envelope("grade", str(run_dir), "--score-card", str(card), "--json")

    assert status == 1
    assert codes(payload) == ["metric_not_found"]
    assert payload["problems"][0]["subject"] == "headline_accuracy"
    assert payload["problems"][0]["path"] == str(card)


def test_the_human_output_is_untouched_by_any_of_this():
    """The flag adds a reader and replaces none. Every command here still prints what it
    printed before, which `test_readme_console.py` checks against the README itself."""
    result = runner.invoke(app, ["validate", str(EXAMPLE_PLAN), "-m", str(PACKS)])

    assert result.exit_code == 0
    assert result.output == f"{EXAMPLE_PLAN}: ok, 1 pack(s)\n"
    assert "{" not in result.output
