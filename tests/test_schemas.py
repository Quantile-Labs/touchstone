"""The published JSON Schemas still say what the contracts say.

An editor validates a plan against `docs/schemas/plan.schema.json` and `touchstone
validate` validates it against `contracts/plan.py`. The schema is generated from the
contract so the two cannot disagree, and this is the test that notices when the generated
file on disk has fallen behind the model it came from. A stale schema is worse than none:
it green-lights a key the tool will reject, or flags one the tool accepts, and the author
believes the editor.
"""

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "docs" / "schemas"
GENERATOR = ROOT / "scripts" / "gen_schemas.py"

BASE_URL = "https://touchstone.quantilelabs.com/schemas"

AUTHORED = {
    ROOT / "examples" / "plan.yaml": "plan",
    ROOT / "examples" / "scorecard.yaml": "scorecard",
    ROOT / "packs" / "example_pack" / "manifest.yaml": "pack-manifest",
}
"""Every file in this repository a person writes by hand, and the schema that describes
it. `audit` has no example here yet; its schema is generated and published all the same,
because the file an assessor fills in is written outside this repository."""


def _schemas() -> dict[str, dict]:
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in _paths()}


def _paths() -> list[Path]:
    return sorted(SCHEMAS.glob("*.schema.json"))


def test_the_committed_schemas_match_the_contracts():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"], capture_output=True, text=True, cwd=ROOT
    )
    assert result.returncode == 0, result.stderr


def test_every_schema_names_the_url_it_is_published_at():
    """`$id` is what an editor resolves a relative `$ref` against, and what a reader
    checks a downloaded copy against. A wrong one points at somebody else's file."""
    for path in _paths():
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["$id"] == f"{BASE_URL}/{path.name}", path.name
        assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema", path.name


def test_the_schemas_carry_the_documentation_the_contracts_write():
    """The field docstrings in `contracts/` are the hover text in an editor, and they only
    reach the schema while the models set `use_attribute_docstrings`. Losing that leaves a
    schema that still validates and teaches nobody anything, which no other test sees."""
    plan = _schemas()["plan.schema.json"]
    assert plan["properties"]["access_tier"]["description"].startswith("No claim in the report")

    card = _schemas()["scorecard.schema.json"]
    min_n = card["$defs"]["MetricRef"]["properties"]["min_n"]
    assert "smallest cell" in min_n["description"]


def test_every_authored_example_points_at_a_schema_that_exists():
    for path, stem in AUTHORED.items():
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first == f"# yaml-language-server: $schema={BASE_URL}/{stem}.schema.json", path.name
        assert (SCHEMAS / f"{stem}.schema.json").exists()


def test_the_modeline_is_a_comment_and_changes_nothing():
    """It is the first line of files the README quotes and the test suite loads. A reader
    who cannot see the modeline in the parsed document is the whole point of using one."""
    for path in AUTHORED:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        assert not any("yaml-language-server" in str(key) for key in document)
