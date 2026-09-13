import shutil
from pathlib import Path

from typer.testing import CliRunner

from touchstone.cli import app
from touchstone.contracts import Manifest, Plan
from touchstone.plan_check import check

EXAMPLE_PLAN = Path(__file__).resolve().parents[1] / "examples" / "plan.yaml"

PLAN = {
    "plan_name": "demo",
    "access_tier": "black_box",
    "systems": {"chatbot": {"type": "llm_api"}},
    "packs": [
        {
            "id": "procedural_ng",
            "image": "example/procedural_ng:1.0",
            "systems": {"system_under_test": "chatbot"},
            "params": {"max_items": 50},
        }
    ],
}

MANIFEST = {
    "name": "procedural_ng",
    "version": "1.0",
    "input_systems": [{"name": "system_under_test", "type": "llm_api", "required": True}],
    "input_schema": [{"name": "max_items", "type": "integer"}],
}


def manifests(**overrides):
    data = MANIFEST | overrides
    return {"procedural_ng": Manifest.model_validate(data)}


def messages(problems):
    """The sentences alone. Every problem is a `Problem` now, and most of these tests are
    about what the reader is told rather than about where it points."""
    return [problem.message for problem in problems]


def test_accepts_a_valid_plan():
    assert check(Plan.model_validate(PLAN), manifests()) == []


def test_rejects_an_unknown_parameter():
    plan = Plan.model_validate(PLAN | {"packs": [PLAN["packs"][0] | {"params": {"nope": 1}}]})
    problems = check(plan, manifests())
    assert [(problem.code, problem.message) for problem in problems] == [
        ("parameter_unknown", "procedural_ng: pack does not accept parameter 'nope'")
    ]


def test_rejects_a_missing_required_system():
    plan = Plan.model_validate(PLAN | {"packs": [PLAN["packs"][0] | {"systems": {}}]})
    problems = check(plan, manifests())
    assert "procedural_ng: missing required system 'system_under_test'" in messages(problems)
    assert "system_missing" in {problem.code for problem in problems}


def test_rejects_a_system_not_defined_in_the_plan():
    pack = PLAN["packs"][0] | {"systems": {"system_under_test": "ghost"}}
    plan = Plan.model_validate(PLAN | {"packs": [pack]})
    problems = check(plan, manifests())
    assert "procedural_ng: system 'ghost' is not defined in the plan" in messages(problems)
    assert "system_undefined" in {problem.code for problem in problems}


def test_rejects_a_plan_naming_an_unknown_pack():
    plan = Plan.model_validate(PLAN)
    problems = check(plan, {})
    assert [(problem.code, problem.message) for problem in problems] == [
        ("pack_manifest_missing", "procedural_ng: no manifest found")
    ]


def test_a_missing_manifest_names_the_file_it_expected(tmp_path):
    problems = check(Plan.model_validate(PLAN), {}, None, tmp_path / "packs")
    expected = tmp_path / "packs" / "procedural_ng" / "manifest.yaml"
    assert messages(problems) == [f"procedural_ng: no manifest at {expected}"]


def test_validate_finds_the_packs_above_the_plan_from_another_directory(tmp_path, monkeypatch):
    """The README quick start typed outside the repository used to report no manifest."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["validate", str(EXAMPLE_PLAN)])

    assert result.exit_code == 0, result.output


def test_validate_without_a_packs_directory_says_what_to_pass(tmp_path, monkeypatch):
    shutil.copy(EXAMPLE_PLAN, tmp_path / "plan.yaml")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["validate", "plan.yaml"])

    assert result.exit_code == 1
    assert "--manifests" in result.output
