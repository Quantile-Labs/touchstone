"""Calibration, ECE, and the confident-and-wrong rate."""

import pytest

from touchstone.contracts import ItemRecord
from touchstone.stats.calibration import calibration, confident_and_wrong


def _item(index, confidence, correct, **extra):
    return ItemRecord(
        item_id=f"i{index}",
        confidence=confidence,
        outcome={"correct": correct},
        **extra,
    )


def _perfectly_calibrated():
    """Ten bins; in the bin centred on c, exactly c of the answers are right."""
    items = []
    for bin_index in range(10):
        confidence = bin_index / 10 + 0.05
        right = round(confidence * 100)
        for offset in range(100):
            items.append(_item(f"{bin_index}.{offset}", confidence, offset < right))
    return items


def test_a_calibrated_system_has_no_calibration_error():
    curve = calibration(_perfectly_calibrated(), "correct")
    assert curve.ece == pytest.approx(0.0, abs=1e-12)
    assert curve.n == 1000
    assert len(curve.bins) == 10


def test_an_overconfident_system_is_measured_as_overconfident():
    items = [_item(index, 0.95, index < 60) for index in range(100)]
    curve = calibration(items, "correct")
    assert curve.ece == pytest.approx(0.35, abs=1e-9)
    assert len(curve.bins) == 1
    assert curve.bins[0].gap == pytest.approx(0.35, abs=1e-9)


def test_a_confidence_of_one_lands_in_the_top_bin_rather_than_off_the_end():
    curve = calibration([_item(0, 1.0, True)], "correct")
    assert len(curve.bins) == 1
    assert (curve.bins[0].low, curve.bins[0].high) == (0.9, 1.0)


def test_items_without_a_confidence_are_counted_rather_than_dropped():
    items = [_item(0, 0.9, True), _item(1, None, False), _item(2, None, True)]
    curve = calibration(items, "correct")
    assert (curve.n, curve.unscored) == (1, 2)


def test_an_unreported_outcome_is_in_no_denominator():
    items = [_item(0, 0.9, True), ItemRecord(item_id="other", confidence=0.9)]
    curve = calibration(items, "correct")
    assert curve.n == 1


def test_nothing_scored_has_no_calibration_error():
    curve = calibration([ItemRecord(item_id="a", outcome={"correct": True})], "correct")
    assert curve.ece is None
    assert (curve.n, curve.unscored) == (0, 1)


def test_calibration_names_its_estimator_and_cites_it():
    curve = calibration(_perfectly_calibrated(), "correct")
    assert curve.estimator == "ece_equal_width"
    assert curve.parameters["bins"] == 10
    assert "Naeini" in curve.reference


def test_confident_and_wrong_counts_only_the_confident_failures():
    items = [
        _item(0, 0.95, False),  # confident and wrong
        _item(1, 0.95, True),  # confident and right
        _item(2, 0.20, False),  # wrong, but it said so
        _item(3, None, False),  # never scored, so never counted
    ]
    assert confident_and_wrong(items, "correct", threshold=0.9) == (1, 3)


def test_the_threshold_moves_the_count():
    items = [_item(0, 0.5, False), _item(1, 0.95, False)]
    assert confident_and_wrong(items, "correct", threshold=0.9)[0] == 1
    assert confident_and_wrong(items, "correct", threshold=0.4)[0] == 2


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_an_impossible_threshold_is_refused(threshold):
    with pytest.raises(ValueError):
        confident_and_wrong([], "correct", threshold=threshold)


def test_zero_bins_is_refused():
    with pytest.raises(ValueError):
        calibration([], "correct", bins=0)
