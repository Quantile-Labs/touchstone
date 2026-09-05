"""Indicators a person assesses, and the two things the engine still checks about them.

`contestability` and `artefact_provenance` are read off an organisation rather than off
`items.jsonl`, so the level arrives from an assessor. What the engine refuses to give up is
the vocabulary and the ceiling: a level that is not on the score card's ladder is an error,
and an audited level is capped by the access tier exactly like a computed one. The second
is the point. No tier reaches the top level for `artefact_provenance`, because a white box
evaluation still cannot show that the artefact it read is the artefact serving traffic.
"""

import json

import pytest
import yaml
from test_grade import LEVELS, bundle, rate
from typer.testing import CliRunner

from touchstone.cli import app
from touchstone.contracts.audit import AuditResponses
from touchstone.contracts.scorecard import ScoreCard
from touchstone.errors import ScoreCardError
from touchstone.grade import check, grade, lines

runner = CliRunner()


def card(**extra):
    return ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        indicators=[
            {
                "id": "artefact_provenance",
                "metric": {
                    "source": "audit",
                    "question": "Is the artefact evaluated the artefact deployed?",
                },
            }
        ],
        **extra,
    )


def responses(level="A", indicator="artefact_provenance"):
    return AuditResponses(
        audit_name="test audit",
        assessor="an assessor",
        assessed_utc="2026-08-26T00:00:00Z",
        responses={indicator: {"level": level, "evidence": "read the deployment records"}},
    )


def test_an_audit_indicator_with_no_responses_is_ungraded_and_says_why():
    scored = grade(card(), bundle(), "black_box").indicators[0]

    assert scored.verdict == "ungraded"
    assert scored.level is None
    assert "--audit" in scored.reason


def test_an_audited_level_is_graded_and_carries_the_evidence_behind_it():
    scored = grade(card(), bundle(), "black_box", audit=responses(level="B")).indicators[0]

    assert scored.verdict == "graded"
    assert scored.level == "B"
    assert scored.audit.evidence == "read the deployment records"


def test_an_audited_level_is_capped_by_the_access_tier_like_a_computed_one():
    """The whole reason the engine touches an audit outcome at all. An assessor may
    conclude anything; what a black box evaluation may claim is still bounded."""
    scored = grade(
        card(tier_ceilings={"black_box": "C"}),
        bundle(),
        "black_box",
        audit=responses(level="A"),
    ).indicators[0]

    assert scored.level == "C"
    assert scored.uncapped_level == "A"
    assert scored.ceiling_reason == "access_tier"


def test_a_level_the_score_card_does_not_declare_is_an_error():
    with pytest.raises(ScoreCardError) as raised:
        grade(card(), bundle(), "black_box", audit=responses(level="excellent"))

    assert "ladder" in str(raised.value)


def test_a_response_for_an_indicator_the_card_computes_is_refused():
    """An assessor cannot overrule a measurement. The response would be silently ignored
    otherwise, which is the class of defect every refusal in `check` is about."""
    computed = ScoreCard(
        score_card_name="test",
        levels=LEVELS,
        indicators=[
            {
                "id": "headline",
                "metric": {"name": "correct", "pack_id": "procedural_ng"},
                "assessment": [{"level": "A", "condition": "greater_equal", "threshold": 0.5}],
            }
        ],
    )
    problems = check(
        computed,
        bundle(rate("correct", 0.9, 0.85, 0.93)),
        "black_box",
        responses(indicator="headline"),
    )

    assert any("computes from the bundle" in problem.message for problem in problems)


def test_a_response_naming_an_indicator_the_card_never_declared_is_refused():
    problems = check(card(), bundle(), "black_box", responses(indicator="invented"))

    assert any("does not declare" in problem.message for problem in problems)


def test_an_audit_answering_a_different_indicator_leaves_this_one_unassessed():
    scored = grade(
        card(), bundle(), "black_box", audit=responses(indicator="contestability")
    ).indicators[0]

    assert scored.verdict == "ungraded"
    assert "nobody has assessed it" in scored.reason


def test_an_audit_indicator_may_not_carry_rules():
    with pytest.raises(Exception) as raised:
        ScoreCard(
            score_card_name="test",
            levels=LEVELS,
            indicators=[
                {
                    "id": "artefact_provenance",
                    "metric": {"source": "audit", "question": "is it?"},
                    "assessment": [{"level": "A", "condition": "greater_equal", "threshold": 0.5}],
                }
            ],
        )

    assert "assessor" in str(raised.value)


def test_a_computed_indicator_still_needs_rules():
    with pytest.raises(Exception) as raised:
        ScoreCard(
            score_card_name="test",
            levels=LEVELS,
            indicators=[{"id": "headline", "metric": {"name": "correct"}}],
        )

    assert "nothing to grade with" in str(raised.value)


def test_an_audited_indicator_prints_its_level_without_a_number():
    scorecard = grade(card(), bundle(), "black_box", audit=responses(level="B"))

    assert lines(scorecard)[0] == "artefact_provenance: B"


AUDIT_FILE = {
    "audit_name": "QL audit 001",
    "assessor": "an assessor",
    "assessed_utc": "2026-08-26T00:00:00Z",
    "responses": {"artefact_provenance": {"level": "B", "evidence": "read the deployment records"}},
}

SCORE_CARD = """
score_card_name: "audited card"
levels: ["A", "B", "C", "D"]
tier_ceilings:
  black_box: "A"
indicators:
  - id: artefact_provenance
    metric: {source: audit, question: "Is the artefact evaluated the artefact deployed?"}
"""


def run_dir(tmp_path):
    from test_grade_cli import ESTIMATES, LOCK

    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "estimates.json").write_text(json.dumps(ESTIMATES))
    (directory / "plan.lock.json").write_text(json.dumps(LOCK))
    card_path = tmp_path / "card.yaml"
    card_path.write_text(SCORE_CARD)
    audit_path = tmp_path / "elsewhere" / "audit.yaml"
    audit_path.parent.mkdir()
    audit_path.write_text(yaml.safe_dump(AUDIT_FILE))
    return directory, card_path, audit_path


def test_the_responses_are_copied_into_the_run_and_hashed(tmp_path):
    """A grade read out of a file on the assessor's laptop cannot be recomputed from the
    bundle, which is the one thing every other input to this command already avoids."""
    directory, card_path, audit_path = run_dir(tmp_path)

    result = runner.invoke(
        app,
        ["grade", str(directory), "--score-card", str(card_path), "--audit", str(audit_path)],
    )

    assert result.exit_code == 0, result.output
    assert (directory / "audit.yaml").read_text() == audit_path.read_text()

    written = json.loads((directory / "scorecard.json").read_text())
    assert written["audit_name"] == "QL audit 001"
    assert written["audit_assessor"] == "an assessor", (
        "a judgment with no author cannot be questioned"
    )
    assert len(written["audit_sha256"]) == 64
    assert written["indicators"][0]["level"] == "B"


def test_grading_twice_over_the_copy_already_in_the_run_does_not_fail(tmp_path):
    """`copy_plan` had exactly this defect: a file copied onto itself raises, and it fired
    after the work was done. The same sequence is the natural second run here."""
    directory, card_path, audit_path = run_dir(tmp_path)
    runner.invoke(
        app,
        ["grade", str(directory), "--score-card", str(card_path), "--audit", str(audit_path)],
    )

    again = runner.invoke(
        app,
        [
            "grade",
            str(directory),
            "--score-card",
            str(card_path),
            "--audit",
            str(directory / "audit.yaml"),
        ],
    )

    assert again.exit_code == 0, again.output
