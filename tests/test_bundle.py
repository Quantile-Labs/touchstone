import json

import pytest

from touchstone import bundle
from touchstone.errors import BundleError


def sealed(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    bundle.seal(root)
    return root


def test_seals_every_file_under_the_root(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x", "traces/a.json": "{}"})
    manifest = bundle.load_manifest(root)
    assert [entry.path for entry in manifest.files] == ["items.jsonl", "traces/a.json"]
    assert manifest.sha256 == bundle.bundle_hash(manifest.files)


def test_a_sealed_bundle_verifies(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": '{"item_id": "a"}\n'})
    assert bundle.verify(root) == []


def test_the_bundle_hash_ignores_the_seal_time(tmp_path):
    first = sealed(tmp_path / "a", {"items.jsonl": "x"})
    second = sealed(tmp_path / "b", {"items.jsonl": "x"})
    assert bundle.load_manifest(first).sha256 == bundle.load_manifest(second).sha256


def test_refuses_to_seal_twice(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    with pytest.raises(BundleError):
        bundle.seal(root)


def test_refuses_to_seal_nothing(tmp_path):
    with pytest.raises(BundleError):
        bundle.seal(tmp_path)


def test_refuses_to_seal_a_symlink(tmp_path):
    (tmp_path / "items.jsonl").write_text("x")
    (tmp_path / "elsewhere").symlink_to(tmp_path / "items.jsonl")
    with pytest.raises(BundleError):
        bundle.seal(tmp_path)


def test_detects_a_modified_file(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": '{"score": 0.87}\n'})
    (root / "items.jsonl").write_text('{"score": 0.88}\n')
    failures = bundle.verify(root)
    assert [(f.code, f.subject, f.message) for f in failures] == [
        ("file_hash_mismatch", "items.jsonl", "hash mismatch: items.jsonl")
    ]


def test_detects_a_missing_file(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    (root / "items.jsonl").unlink()
    failures = bundle.verify(root)
    assert [(f.code, f.subject) for f in failures] == [("file_missing", "items.jsonl")]


def test_detects_an_unrecorded_file(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    (root / "extra.txt").write_text("added later")
    failures = bundle.verify(root)
    assert [(f.code, f.subject) for f in failures] == [("file_not_recorded", "extra.txt")]


def test_detects_an_edited_manifest_entry(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    path = root / bundle.MANIFEST_NAME
    record = json.loads(path.read_text())
    record["files"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(record))
    assert "bundle_hash_mismatch" in {failure.code for failure in bundle.verify(root)}


def test_fails_closed_without_a_manifest(tmp_path):
    with pytest.raises(BundleError):
        bundle.verify(tmp_path)


def test_fails_closed_on_a_malformed_manifest(tmp_path):
    (tmp_path / bundle.MANIFEST_NAME).write_text('{"files": []}')
    with pytest.raises(BundleError):
        bundle.verify(tmp_path)


def test_rejects_a_path_that_escapes_the_bundle(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    path = root / bundle.MANIFEST_NAME
    record = json.loads(path.read_text())
    record["files"][0]["path"] = "../outside.txt"
    path.write_text(json.dumps(record))
    with pytest.raises(BundleError):
        bundle.verify(root)


def ledger(root, *events):
    path = root / "ledger" / "RUNLOG.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({"utc": "now", "event": event}) + "\n" for event in events))
    return root


def test_refuses_to_seal_a_run_that_never_finished(tmp_path):
    """The defect this guards: a crashed run leaves files that hash perfectly well, and a
    bundle sealed over them is a failed run presenting itself as evidence that verifies."""
    (tmp_path / "items.jsonl").write_text('{"item_id": "a"}\n')
    ledger(tmp_path, "run_started", "unit_started")

    with pytest.raises(BundleError) as raised:
        bundle.seal(tmp_path)

    assert "never finished" in str(raised.value)
    assert "unit_started" in str(raised.value), "say where the ledger stopped"
    assert not (tmp_path / bundle.MANIFEST_NAME).exists()


def test_seals_a_run_whose_units_failed_but_whose_harness_finished(tmp_path):
    """A unit that exits non-zero is a result. The guard is about the harness dying, not
    about the pack failing, and conflating the two would refuse to seal a real finding."""
    (tmp_path / "items.jsonl").write_text('{"item_id": "a"}\n')
    ledger(tmp_path, "run_started", "unit_started", "unit_failed", "run_finished")

    assert bundle.seal(tmp_path).run_ledger == "complete"


def test_a_hand_built_directory_seals_and_says_it_was_not_a_run(tmp_path):
    """Sealing files that came from somewhere else stays legitimate. What changes is that
    the manifest no longer lets it pass for something this tool ran."""
    root = sealed(tmp_path, {"items.jsonl": "x"})
    assert bundle.load_manifest(root).run_ledger == "absent"


def test_an_unreadable_ledger_is_an_error_and_not_an_absent_one(tmp_path):
    (tmp_path / "items.jsonl").write_text("x")
    (tmp_path / "ledger").mkdir()
    (tmp_path / "ledger" / "RUNLOG.jsonl").write_text("{not json\n")

    with pytest.raises(BundleError):
        bundle.seal(tmp_path)
