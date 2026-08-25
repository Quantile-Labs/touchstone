"""Stamping the plan hash.

Driven against a stand-in `ots` so the suite needs neither the client nor a network. The
real client is checked by hand; what is tested here is that the receipt and the file it
covers end up together, and that a missing or failing `ots` fails closed rather than
leaving a bundle that looks anchored and is not.
"""

import os
import stat
from pathlib import Path

import pytest

from touchstone import anchor
from touchstone.errors import AnchorError

HASH_LINE = "ce0eba72a495a80c45c2ec945af5cde97d9ce15ee3198d6195918904f2590a56  plan.lock.json\n"


def fake_ots(tmp_path: Path, script: str) -> str:
    """A stand-in on PATH, so nothing here depends on the real client."""
    binary = tmp_path / "bin" / "ots"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(script)
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return str(binary)


def hash_file(tmp_path: Path) -> Path:
    path = tmp_path / "PLAN.sha256"
    path.write_text(HASH_LINE)
    return path


WRITES_RECEIPT = '#!/bin/sh\nprintf "receipt" > "$2.ots"\n'
WRITES_NOTHING = "#!/bin/sh\nexit 0\n"
FAILS = '#!/bin/sh\necho "calendar unreachable" >&2\nexit 1\n'


def test_the_receipt_sits_beside_the_file_it_covers(tmp_path):
    receipt = anchor.stamp(hash_file(tmp_path), tmp_path, binary=fake_ots(tmp_path, WRITES_RECEIPT))
    assert receipt.name == "PLAN.sha256.ots"
    assert (receipt.parent / "PLAN.sha256").read_text() == HASH_LINE


def test_the_stamped_copy_is_the_file_that_was_hashed(tmp_path):
    """anchors/ has to verify on its own, years later, without the rest of the bundle."""
    anchor.stamp(hash_file(tmp_path), tmp_path, binary=fake_ots(tmp_path, WRITES_RECEIPT))
    anchors = tmp_path / anchor.ANCHORS_DIR
    assert (anchors / "PLAN.sha256").read_text() == (tmp_path / "PLAN.sha256").read_text()


def test_it_says_a_fresh_receipt_is_not_yet_a_bitcoin_proof(tmp_path):
    """A receipt that looks stronger than it is would be the exact failure this tool sells
    against, so the caveat ships inside the bundle rather than in our documentation."""
    anchor.stamp(hash_file(tmp_path), tmp_path, binary=fake_ots(tmp_path, WRITES_RECEIPT))
    note = (tmp_path / anchor.ANCHORS_DIR / anchor.NOTE_NAME).read_text()
    assert "ots upgrade" in note
    assert "not a bitcoin" in note.lower()


def test_fails_closed_when_ots_is_missing(tmp_path):
    with pytest.raises(AnchorError, match="not on PATH"):
        anchor.stamp(hash_file(tmp_path), tmp_path, binary=str(tmp_path / "no" / "such" / "ots"))


def test_fails_closed_when_ots_errors(tmp_path):
    with pytest.raises(AnchorError, match="calendar unreachable"):
        anchor.stamp(hash_file(tmp_path), tmp_path, binary=fake_ots(tmp_path, FAILS))


def test_fails_closed_when_ots_exits_clean_but_writes_no_receipt(tmp_path):
    with pytest.raises(AnchorError, match="no receipt"):
        anchor.stamp(hash_file(tmp_path), tmp_path, binary=fake_ots(tmp_path, WRITES_NOTHING))


def test_fails_closed_when_there_is_nothing_to_stamp(tmp_path):
    with pytest.raises(AnchorError, match="does not exist"):
        anchor.stamp(tmp_path / "PLAN.sha256", tmp_path, binary="ots")


@pytest.mark.skipif(not os.environ.get("TOUCHSTONE_TEST_OTS"), reason="needs ots and a network")
def test_against_the_real_client(tmp_path):
    receipt = anchor.stamp(hash_file(tmp_path), tmp_path)
    assert receipt.stat().st_size > 0
