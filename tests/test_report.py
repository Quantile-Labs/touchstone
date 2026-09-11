"""`touchstone report`, and the document it sets.

Two things are worth testing here and the layout is not one of them. The first is that
every finding is decided by something in the bundle, so an empty directory fails almost
every practice item and a complete one does not. The second is that no number on the page
was invented: every figure the document sets is traced back to a field in `estimates.json`
or `scorecard.json`.
"""

import json
import re
import shutil
import zlib
from pathlib import Path

import pytest
from conftest import StubBackend
from typer.testing import CliRunner

from touchstone import report
from touchstone import run as run_plan
from touchstone.cli import app
from touchstone.contracts.environment import Environment, PackCost, RunCost
from touchstone.contracts.scorecard import (
    Difference,
    GradedIndicator,
    Measured,
    MetricRef,
    Scorecard,
)
from touchstone.errors import BundleError

runner = CliRunner()

GOLDEN = Path(__file__).resolve().parent / "golden" / "run-001"


@pytest.fixture
def bundle(tmp_path) -> Path:
    """A copy of the golden bundle, so a test can edit it without unsealing the original.

    Named `bundle` rather than `run` because the `graded` fixture in conftest builds a run
    directory of its own and two fixtures cannot own the same path.
    """
    copy = tmp_path / "bundle"
    shutil.copytree(GOLDEN, copy)
    return copy


def text_of(pdf: bytes) -> str:
    """Everything the document actually sets, pulled back out of the content streams.

    Reading the produced file rather than the objects that built it, because a figure that
    is computed correctly and then set into the wrong column is still a wrong page.
    """
    out = []
    for stream in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S):
        body = zlib.decompress(stream).decode("latin-1")
        out.extend(re.findall(r"\((.*?)\) Tj", body))
    return "\n".join(out)


def test_an_empty_directory_fails_almost_every_practice_item(tmp_path):
    """The trap this was written against. A statement that only lists what passed is
    marketing, and the first reader to diff it against the practice list will say so."""
    stated = report.conformance(tmp_path)

    assert stated.met == 0
    assert stated.unmet >= 8
    assert {finding.status for finding in stated.findings} == {"not met", "not applicable"}


def test_a_complete_bundle_still_fails_the_items_this_tool_does_not_satisfy(bundle):
    stated = report.conformance(bundle)
    failing = {finding.code for finding in stated.findings if finding.status == "not met"}

    assert "assumption_checks" in failing, "the bundle records the estimator, not its premises"


def cost_finding(bundle_dir: Path):
    return next(f for f in report.conformance(bundle_dir).findings if f.code == "costs_recorded")


def with_cost(bundle_dir: Path, cost: RunCost | None) -> None:
    environment = Environment(
        touchstone_version="test",
        python="3.12",
        platform="test",
        backend="stub",
        isolation="none",
        plan_hash="0" * 64,
        cost=cost,
    )
    (bundle_dir / "environment.json").write_text(environment.model_dump_json())


def one_pack(items_costed: int, totals: dict[str, float]) -> RunCost:
    pack = PackCost(
        pack_id="example_pack",
        units=2,
        wall_seconds=12.5,
        items=400,
        items_costed=items_costed,
        totals=totals,
    )
    return RunCost(wall_seconds=12.5, packs=[pack])


def test_a_bundle_with_no_environment_cannot_say_what_the_run_cost(bundle):
    finding = cost_finding(bundle)
    assert finding.status == "not met"
    assert "no environment.json" in finding.detail


def test_an_environment_written_before_cost_was_recorded_records_none(bundle):
    with_cost(bundle, None)
    finding = cost_finding(bundle)
    assert finding.status == "not met"
    assert "before cost was recorded" in finding.detail


def test_wall_time_without_what_every_row_spent_does_not_meet_the_item(bundle):
    """One row short is enough. A total over 399 of 400 rows undercounts by an amount
    nobody knows, and a reader pricing the run from it is pricing the wrong run."""
    with_cost(bundle, one_pack(items_costed=399, totals={"input_tokens": 47880.0}))
    finding = cost_finding(bundle)

    assert finding.status == "not met"
    assert "12.5 seconds of wall time across 2 units" in finding.detail
    assert "example_pack put a cost on 399 of 400 rows" in finding.detail


def test_a_cost_on_every_row_meets_the_item_and_states_the_totals(bundle):
    with_cost(bundle, one_pack(items_costed=400, totals={"input_tokens": 48000.0, "usd": 0.0021}))
    finding = cost_finding(bundle)

    assert finding.status == "met"
    assert "input_tokens 48,000" in finding.detail
    assert "usd 0.0021" in finding.detail
    assert finding.evidence == ["environment.json", "items.jsonl"]


def test_the_report_reads_the_cost_a_run_writes(frozen, tmp_path):
    """The two halves meet here: what `run` writes is what `report` reads."""
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend(cost={"tokens": 12}))
    finding = cost_finding(out)

    assert finding.status == "met"
    assert "example_pack tokens 24" in finding.detail


def with_movement(bundle_dir: Path, *comparisons: str) -> None:
    measured = [
        Measured(
            ref=MetricRef(source="paired_difference", name="correct"),
            value=0.05,
            low=0.01,
            high=0.09,
            n=400,
            difference=Difference(
                comparison=comparison,
                reason=f"{comparison} for this test",
                estimator="test",
                reference="test",
            ),
        )
        for comparison in comparisons
    ]
    scorecard = Scorecard(
        touchstone_version="test",
        score_card_name="test",
        access_tier="black_box",
        levels=["A", "B"],
        plan_sha256="a" * 64,
        prior_plan_sha256="a" * 64,
        indicators=[GradedIndicator(id="held", verdict="graded", level="A", measured=measured)],
    )
    (bundle_dir / "scorecard.json").write_text(scorecard.model_dump_json())


def movement_finding(bundle_dir: Path):
    return next(f for f in report.conformance(bundle_dir).findings if f.code == "paired_difference")


def test_movement_estimated_as_a_paired_difference_meets_the_item(bundle):
    with_movement(bundle, "paired")
    finding = movement_finding(bundle)
    assert finding.status == "met"
    assert "paired for this test" in finding.detail


def test_one_unpaired_movement_is_enough_to_fail_the_item(bundle):
    with_movement(bundle, "paired", "unpaired")
    finding = movement_finding(bundle)
    assert finding.status == "not met"
    assert "1 of 2 movement figures" in finding.detail
    assert "unpaired for this test" in finding.detail


def test_movement_graded_with_no_paired_source_does_not_meet_the_item(bundle):
    with_movement(bundle)
    finding = movement_finding(bundle)
    assert finding.status == "not met"
    assert "no indicator reads a paired_difference" in finding.detail


def test_every_practice_item_appears_exactly_once(bundle):
    codes = [finding.code for finding in report.conformance(bundle).findings]
    assert len(codes) == len(set(codes))
    assert len(codes) == 10


def image_finding(bundle_dir: Path):
    return next(f for f in report.conformance(bundle_dir).findings if f.code == "code_and_image")


def test_a_bundle_with_no_lock_cannot_say_what_ran(bundle):
    finding = image_finding(bundle)
    assert finding.status == "not met"
    assert "plan.lock.json" in finding.detail


def test_an_unpublished_image_is_not_an_obtainable_one(bundle, graded):
    """A digest pins what ran. It does not make it fetchable, and a reader holding the
    bundle and no registry cannot rerun anything."""
    run_dir, _ = graded
    shutil.copy(run_dir / "plan.lock.json", bundle / "plan.lock.json")

    finding = image_finding(bundle)
    assert finding.status == "not met"
    assert "registry" in finding.detail


def test_an_image_named_with_a_registry_satisfies_the_item(bundle, graded):
    run_dir, _ = graded
    lock = json.loads((run_dir / "plan.lock.json").read_text())
    lock["packs"][0]["image"] = "ghcr.io/quantile-labs/" + lock["packs"][0]["image"]
    (bundle / "plan.lock.json").write_text(json.dumps(lock))

    assert image_finding(bundle).status == "met"


def test_a_bundle_whose_hashes_fail_says_so(bundle):
    (bundle / "items.jsonl").write_text("tampered\n")
    assert report.conformance(bundle).verified is False


def test_every_rate_on_the_page_is_one_the_bundle_holds(bundle, tmp_path):
    """The document sets figures and never computes them. Each rate printed has to be a
    point estimate in `estimates.json`, rounded, and each denominator has to be its n."""
    out = tmp_path / "statement.pdf"
    report.write(bundle, out)
    printed = text_of(out.read_bytes())

    estimates = json.loads((bundle / "estimates.json").read_text())["estimates"]
    assert estimates, "the golden bundle should hold estimates to check against"
    for estimate in estimates:
        if estimate["point"] is None:
            continue
        assert f"{estimate['point'] * 100:.1f}%" in printed
        assert f"{estimate['low'] * 100:.1f} to {estimate['high'] * 100:.1f}" in printed
        assert str(estimate["n"]) in printed


def test_the_document_names_the_bundle_and_its_hash(bundle, tmp_path):
    out = tmp_path / "statement.pdf"
    stated = report.write(bundle, out)
    printed = text_of(out.read_bytes())

    assert stated.bundle_sha256 in printed
    assert "CONFORMANCE STATEMENT" in printed
    assert "NIST AI 800-2" in printed


def test_the_same_bundle_sets_the_same_bytes(bundle, tmp_path):
    """No creation date and no document identifier, so a statement can be hashed and two
    readers can agree they are holding the same one."""
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    report.write(bundle, first)
    report.write(bundle, second)
    assert first.read_bytes() == second.read_bytes()


def test_it_refuses_to_write_inside_the_bundle(bundle):
    """A file the manifest does not record makes the bundle fail its own verification, so
    the statement would break the thing it describes."""
    with pytest.raises(BundleError, match="inside"):
        report.write(bundle, bundle / "statement.pdf")


def test_the_bundle_still_verifies_after_a_statement_is_written(bundle, tmp_path):
    from touchstone import bundle as bundle_files

    report.write(bundle, tmp_path / "statement.pdf")
    assert bundle_files.verify(bundle) == []


def test_the_file_is_a_pdf_a_reader_will_open(bundle, tmp_path):
    out = tmp_path / "statement.pdf"
    report.write(bundle, out)
    raw = out.read_bytes()

    assert raw.startswith(b"%PDF-1.4")
    assert raw.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in raw
    offsets = re.search(rb"startxref\n(\d+)\n", raw)
    assert offsets and raw[int(offsets.group(1)) :].startswith(b"xref"), "the xref is misplaced"


def test_the_cli_writes_a_statement_beside_the_bundle(bundle, tmp_path):
    out = tmp_path / "statement.pdf"
    result = runner.invoke(app, ["report", str(bundle), "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "not met" in result.output


def test_the_cli_reports_unmet_items_as_warnings_and_still_succeeds(bundle, tmp_path):
    """A statement that found failures is a statement that worked."""
    out = tmp_path / "statement.pdf"
    result = runner.invoke(app, ["report", str(bundle), "-o", str(out), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["result"]["not_met"] > 0
    assert {problem["severity"] for problem in payload["problems"]} == {"warning"}
    assert {problem["code"] for problem in payload["problems"]} == {"practice_not_met"}


def test_a_practice_set_this_does_not_know_is_refused(bundle, tmp_path):
    result = runner.invoke(
        app,
        ["report", str(bundle), "-c", "iso-42001", "-o", str(tmp_path / "x.pdf"), "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["problems"][0]["code"] == "bundle_error"
