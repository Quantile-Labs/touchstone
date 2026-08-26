import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_commit_msg.py"


def run(message: str, tmp_path: Path) -> subprocess.CompletedProcess:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)


def test_accepts_a_plain_subject(tmp_path):
    assert run("validate plan against pack manifests\n", tmp_path).returncode == 0


def test_rejects_an_em_dash(tmp_path):
    result = run("add wilson interval — for rates\n", tmp_path)
    assert result.returncode == 1
    assert "em dash" in result.stderr


def test_rejects_ai_attribution(tmp_path):
    result = run("add estimator\n\nGenerated with Claude Code\n", tmp_path)
    assert result.returncode == 1
    assert "AI attribution" in result.stderr


def test_rejects_marketing_adjectives(tmp_path):
    result = run("add comprehensive validation\n", tmp_path)
    assert result.returncode == 1
    assert "comprehensive" in result.stderr


def test_rejects_past_tense(tmp_path):
    result = run("added the plan loader\n", tmp_path)
    assert result.returncode == 1
    assert "imperative" in result.stderr


def test_rejects_a_long_subject(tmp_path):
    result = run("add " + "x" * 80 + "\n", tmp_path)
    assert result.returncode == 1
    assert "hard limit" in result.stderr


def test_rejects_an_x_not_y_subject(tmp_path):
    result = run("put trust at the front, not the sceptic\n", tmp_path)
    assert result.returncode == 1
    assert "slogan" in result.stderr


def test_accepts_a_comma_that_is_not_a_slogan(tmp_path):
    assert run("pin seeds, digests and the plan hash\n", tmp_path).returncode == 0


def test_allows_not_in_the_body(tmp_path):
    message = (
        "add per-indicator tier ceilings\n"
        "\n"
        "A tier mapped to null marks the indicator unassessable there,\n"
        "not failing, so the grade names the tier instead of erroring.\n"
    )
    assert run(message, tmp_path).returncode == 0
