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
    assert bundle.verify(root) == ["hash mismatch: items.jsonl"]


def test_detects_a_missing_file(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    (root / "items.jsonl").unlink()
    assert bundle.verify(root) == ["missing: items.jsonl"]


def test_detects_an_unrecorded_file(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    (root / "extra.txt").write_text("added later")
    assert bundle.verify(root) == ["not recorded: extra.txt"]


def test_detects_an_edited_manifest_entry(tmp_path):
    root = sealed(tmp_path, {"items.jsonl": "x"})
    path = root / bundle.MANIFEST_NAME
    record = json.loads(path.read_text())
    record["files"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(record))
    assert "bundle hash does not match the recorded file list" in bundle.verify(root)


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
