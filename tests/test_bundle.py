import json

import pytest

from touchstone import bundle
from touchstone.errors import BundleError


def write_bundle(root, files):
    entries = []
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        entries.append({"path": name, "sha256": bundle.sha256_file(path)})
    (root / "MANIFEST.json").write_text(json.dumps({"files": entries}))
    return root


def test_verifies_an_intact_bundle(tmp_path):
    root = write_bundle(tmp_path, {"items.jsonl": '{"item_id": "a"}\n'})
    assert bundle.verify(root) == []


def test_detects_a_modified_file(tmp_path):
    root = write_bundle(tmp_path, {"items.jsonl": '{"item_id": "a"}\n'})
    (root / "items.jsonl").write_text('{"item_id": "b"}\n')
    assert bundle.verify(root) == ["hash mismatch: items.jsonl"]


def test_detects_a_missing_file(tmp_path):
    root = write_bundle(tmp_path, {"items.jsonl": "x"})
    (root / "items.jsonl").unlink()
    assert bundle.verify(root) == ["missing: items.jsonl"]


def test_detects_an_unrecorded_file(tmp_path):
    root = write_bundle(tmp_path, {"items.jsonl": "x"})
    (root / "extra.txt").write_text("added later")
    assert bundle.verify(root) == ["not recorded: extra.txt"]


def test_fails_closed_without_a_manifest(tmp_path):
    with pytest.raises(BundleError):
        bundle.verify(tmp_path)
