import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dco.py"

SIGNED = "add wilson interval to rate estimator\n\nSigned-off-by: Ada Lovelace <ada@example.com>\n"


def run(message: str, tmp_path: Path, author: str | None = None) -> subprocess.CompletedProcess:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")
    args = [sys.executable, str(SCRIPT), str(path)]
    if author is not None:
        args.append(author)
    return subprocess.run(args, capture_output=True, text=True)


def test_accepts_a_signed_commit(tmp_path):
    assert run(SIGNED, tmp_path).returncode == 0


def test_rejects_an_unsigned_commit(tmp_path):
    result = run("add wilson interval to rate estimator\n", tmp_path)
    assert result.returncode == 1
    assert "git commit -s" in result.stderr


def test_accepts_a_sign_off_matching_the_author(tmp_path):
    assert run(SIGNED, tmp_path, "Ada Lovelace <ada@example.com>").returncode == 0


def test_rejects_a_sign_off_by_somebody_else(tmp_path):
    """The failure a DCO exists to catch: a trailer pasted from another commit, which
    certifies the wrong person's right to contribute the code."""
    result = run(SIGNED, tmp_path, "Grace Hopper <grace@example.com>")
    assert result.returncode == 1
    assert "did not sign off" in result.stderr


def test_accepts_a_co_author_alongside_the_author(tmp_path):
    message = (
        "add wilson interval to rate estimator\n\n"
        "Signed-off-by: Ada Lovelace <ada@example.com>\n"
        "Signed-off-by: Grace Hopper <grace@example.com>\n"
    )
    assert run(message, tmp_path, "Grace Hopper <grace@example.com>").returncode == 0


def test_rejects_a_hand_typed_approximation(tmp_path):
    """A trailer without the angle brackets is what somebody types when they have read
    about the rule rather than run `git commit -s`, and a DCO bot rejects it after the
    push. Rejecting it here costs a second instead of a round trip."""
    message = "add wilson interval to rate estimator\n\nSigned-off-by: Ada Lovelace\n"
    result = run(message, tmp_path)
    assert result.returncode == 1


def test_ignores_a_sign_off_inside_a_comment(tmp_path):
    """`git commit` appends its own commented block, and a template quoting the trailer
    there would otherwise sign every commit for free."""
    message = "add wilson interval to rate estimator\n\n# Signed-off-by: Ada <ada@example.com>\n"
    assert run(message, tmp_path).returncode == 1
