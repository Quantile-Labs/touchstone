"""BCa. The interval for anything continuous, and it has to reproduce."""

import random

import pytest

from touchstone.stats.bootstrap import bootstrap_bca


def _normal_sample(n=400, mu=3.0, sigma=1.0, seed=11):
    rng = random.Random(seed)
    return [rng.gauss(mu, sigma) for _ in range(n)]


def test_the_same_seed_gives_the_same_interval():
    """An interval nobody else can recompute is not evidence."""
    sample = _normal_sample()
    assert bootstrap_bca(sample, seed=7) == bootstrap_bca(sample, seed=7)


def test_a_different_seed_moves_the_interval_but_not_the_point():
    sample = _normal_sample()
    first = bootstrap_bca(sample, seed=7)
    second = bootstrap_bca(sample, seed=8)
    assert first[0] == second[0]
    assert first[1:] != second[1:]


def test_a_symmetric_sample_agrees_with_the_closed_form():
    """On a large symmetric sample BCa has nothing to correct, so it should land on the
    normal interval. That is the check that the machinery is wired up correctly."""
    sample = _normal_sample(n=2000, seed=5)
    point, low, high = bootstrap_bca(sample, seed=3)
    standard_error = (
        sum((x - point) ** 2 for x in sample) / (len(sample) - 1) / len(sample)
    ) ** 0.5
    assert low == pytest.approx(point - 1.96 * standard_error, abs=0.02)
    assert high == pytest.approx(point + 1.96 * standard_error, abs=0.02)


def test_a_skewed_sample_gets_an_asymmetric_interval():
    """The reason for BCa over the percentile method."""
    rng = random.Random(2)
    sample = [rng.expovariate(1.0) for _ in range(300)]
    point, low, high = bootstrap_bca(sample, seed=3)
    assert (point - low) != pytest.approx(high - point, abs=1e-6)


def test_a_constant_sample_has_a_point_for_an_interval():
    assert bootstrap_bca([2.0] * 40, seed=1) == (2.0, 2.0, 2.0)


def test_a_single_observation_does_not_pretend_to_an_interval():
    assert bootstrap_bca([4.5], seed=1) == (4.5, 4.5, 4.5)


def test_an_empty_sample_is_refused():
    with pytest.raises(ValueError):
        bootstrap_bca([], seed=1)


@pytest.mark.parametrize(("kwargs"), [{"confidence": 0.0}, {"confidence": 1.0}, {"resamples": 0}])
def test_impossible_settings_are_refused(kwargs):
    with pytest.raises(ValueError):
        bootstrap_bca([1.0, 2.0, 3.0], seed=1, **kwargs)
