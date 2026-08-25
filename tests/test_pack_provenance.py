"""Which pack produced an observation, and what follows from knowing.

Before this, `run` concatenated the per-unit files and the merged `items.jsonl` could not
say where a row came from. Two packs both reporting `correct` were pooled into one
denominator, silently, which is the aggregate 02-DESIGN.md section 3 exists to prevent.
"""

import json

import pytest
from conftest import PLAN, StubBackend

from touchstone import freeze as freeze_plan
from touchstone import run as run_plan
from touchstone.contracts import ItemRecord, Plan
from touchstone.errors import EstimateError
from touchstone.estimate import declared_calibration, estimate, load_items


class TwoPacks(StubBackend):
    """Both packs report the same outcome key while measuring different things."""

    def __init__(self, calibrates=None):
        super().__init__()
        self.calibrates = calibrates or {}

    def run(self, spec):
        result = super().run(spec)
        rows = [
            {
                "item_id": f"{spec.pack_id}.{index}",
                "replicate": spec.replicate,
                "outcome": {"correct": index % 2 == 0},
                "confidence": 0.95,
            }
            for index in range(4)
        ]
        (spec.output_dir / "items.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        )
        return result

    def extract_manifest(self, image, manifest_path=""):
        manifest = super().extract_manifest(image, manifest_path)
        manifest.calibrates = self.calibrates.get(image)
        return manifest


def _two_pack_plan():
    plan = json.loads(json.dumps(PLAN))
    second = json.loads(json.dumps(plan["packs"][0]))
    second["id"] = "other_pack"
    second["image"] = "example/other_pack:1.0"
    second["replicates"] = 1
    plan["packs"][0]["replicates"] = 1
    plan["packs"].append(second)
    return Plan.model_validate(plan)


@pytest.fixture
def two_packs(tmp_path):
    backend = TwoPacks()
    lock_dir = tmp_path / "lock"
    freeze_plan.write_lock(freeze_plan.freeze(_two_pack_plan(), backend), lock_dir)
    out = tmp_path / "out"
    assert run_plan.run(lock_dir, out, backend) == []
    return out


def test_every_merged_record_says_which_pack_wrote_it(two_packs):
    packs = {item.pack_id for item in load_items(two_packs)}
    assert packs == {"example_pack", "other_pack"}


def test_a_pack_cannot_name_itself(tmp_path):
    """A pack that could stamp the field could stamp another pack's name, and every rate
    downstream is grouped by it."""
    unit = tmp_path / run_plan.RUNS_DIR / "example_pack-0"
    unit.mkdir(parents=True)
    (unit / "items.jsonl").write_text(
        json.dumps({"item_id": "a", "pack_id": "somebody_else"}) + "\n"
    )

    count, overwritten = run_plan.collect_items(tmp_path, {"example_pack-0": "example_pack"})
    assert (count, overwritten) == (1, 1)
    assert load_items(tmp_path)[0].pack_id == "example_pack"


def test_an_overwritten_claim_reaches_the_ledger(frozen, tmp_path):
    class Liar(StubBackend):
        def run(self, spec):
            result = super().run(spec)
            (spec.output_dir / "items.jsonl").write_text(
                json.dumps({"item_id": "a", "pack_id": "not_me"}) + "\n"
            )
            return result

    out = tmp_path / "out"
    run_plan.run(frozen, out, Liar())
    events = [
        json.loads(line)
        for line in (out / run_plan.LEDGER_DIR / run_plan.RUNLOG_NAME).read_text().splitlines()
    ]
    assert any(event["event"] == "pack_id_overwritten" for event in events)


def test_the_run_carries_the_frozen_plan_into_its_output(frozen, tmp_path):
    """02-DESIGN.md section 6: the bundle is readable without the tool, which a run whose
    plan lives somewhere else is not."""
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    assert (out / freeze_plan.LOCK_NAME).is_file()
    assert (out / freeze_plan.HASH_NAME).is_file()
    assert (out / freeze_plan.LOCK_NAME).read_bytes() == (
        frozen / freeze_plan.LOCK_NAME
    ).read_bytes()


def test_more_than_one_pack_is_marked_as_pooled(two_packs):
    estimates = estimate(load_items(two_packs))
    assert estimates.pooled is True
    assert estimates.packs == ["example_pack", "other_pack"]


def test_each_pack_gets_its_own_denominator(two_packs):
    estimates = estimate(load_items(two_packs))
    per_pack = {
        entry.pack_id: entry
        for entry in estimates.estimates
        if entry.metric == "correct" and not entry.stratum
    }
    assert per_pack["example_pack"].n == 4
    assert per_pack["other_pack"].n == 4
    assert per_pack[None].n == 8  # the pooled figure, kept but marked


def test_a_single_pack_run_names_its_pack_and_does_not_pool(frozen, tmp_path):
    out = tmp_path / "out"
    run_plan.run(frozen, out, StubBackend())
    estimates = estimate(load_items(out))
    assert estimates.pooled is False
    assert estimates.packs == ["example_pack"]


def test_a_hand_built_sample_has_no_pack_and_does_not_pretend_to(tmp_path):
    items = [ItemRecord(item_id="a", outcome={"correct": True})]
    estimates = estimate(items)
    assert estimates.packs == []
    assert estimates.pooled is False


def test_the_frozen_plan_says_what_each_pack_calibrates(tmp_path):
    backend = TwoPacks(calibrates={"example/example_pack@sha256:" + "c" * 64: "correct"})
    lock_dir = tmp_path / "lock"
    freeze_plan.write_lock(freeze_plan.freeze(_two_pack_plan(), backend), lock_dir)
    out = tmp_path / "out"
    run_plan.run(lock_dir, out, backend)

    assert declared_calibration(out) == {"example_pack": "correct", "other_pack": "correct"}


def test_a_run_without_a_lock_declares_nothing(tmp_path):
    assert declared_calibration(tmp_path) == {}


def test_what_the_pack_declared_is_what_gets_calibrated(two_packs):
    items = load_items(two_packs)
    estimates = estimate(items, declared={"example_pack": "correct"})
    assert [(curve.pack_id, curve.metric) for curve in estimates.calibration] == [
        ("example_pack", "correct")
    ]


def test_a_pack_that_declared_nothing_is_not_calibrated(two_packs):
    assert estimate(load_items(two_packs)).calibration == []


def test_an_explicit_target_overrides_what_was_declared(two_packs):
    """Re-analysing an old bundle under a corrected definition needs this."""
    items = load_items(two_packs)
    estimates = estimate(items, calibrate=["correct"], declared={"example_pack": "refused"})
    assert [curve.metric for curve in estimates.calibration] == ["correct"]


def test_a_declared_outcome_no_item_reports_is_refused(two_packs):
    with pytest.raises(EstimateError, match="no item reports it"):
        estimate(load_items(two_packs), declared={"example_pack": "accuracy"})
