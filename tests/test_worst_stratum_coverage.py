"""The simulation that found the defect, kept as the test that it stays fixed.

Ranking strata and reporting the minimum selects on the noise, so the marginal interval
on the winner does not hold its nominal coverage. Under the null this is worst on, every
cell sharing one true rate, a nominal 95 percent Wilson interval over ten equal cells
holds about 69 percent of the time and spends roughly a third of it entirely below the
truth, which a reader takes as a confident finding of a weak group that is not weak.

Seeded, so a failure here is a change in the arithmetic rather than a bad afternoon.
"""

import random

from touchstone.stats.proportion import bonferroni_z, wilson

TRUE_RATE = 0.90
CELL = 180
TRIALS = 2000


def _coverage(strata: int, seed: int = 11) -> tuple[float, float, float]:
    """Coverage of the marginal and the adjusted interval, and how often it lands low."""
    rng = random.Random(seed)
    marginal = adjusted = below = 0
    for _ in range(TRIALS):
        worst = min(rng.binomialvariate(CELL, TRUE_RATE) for _ in range(strata))
        _, low, high = wilson(worst, CELL)
        marginal += low <= TRUE_RATE <= high
        below += high < TRUE_RATE
        _, low, high = wilson(worst, CELL, z=bonferroni_z(strata))
        adjusted += low <= TRUE_RATE <= high
    return marginal / TRIALS, adjusted / TRIALS, below / TRIALS


def test_the_marginal_interval_undercovers_once_cells_are_ranked():
    one, _, _ = _coverage(1)
    ten, _, _ = _coverage(10)
    assert one > 0.93, "a single cell is not a selection and should cover"
    assert ten < 0.80, "ten ranked cells should collapse the coverage, that is the defect"


def test_the_unadjusted_interval_lands_entirely_below_the_truth():
    """The direction that does the damage. A confident finding against an innocent cell."""
    _, _, below = _coverage(10)
    assert below > 0.20


def test_the_adjusted_interval_holds_its_nominal_coverage():
    """Around 96 to 97 percent once cells are ranked, conservative as Bonferroni is.

    The bar is 93 rather than 95 because Wilson's own coverage oscillates with the
    discreteness of the counts and sits at 93.3 percent for a single cell of 180 at this
    rate, before any selection is involved. That figure is the floor the adjustment
    inherits, not something it introduced.
    """
    for strata in (1, 3, 5, 10, 20):
        _, adjusted, _ = _coverage(strata)
        assert adjusted >= 0.93, f"{strata} strata covered {adjusted:.1%}"


def test_the_adjustment_buys_back_what_the_selection_costs():
    for strata in (3, 5, 10, 20):
        marginal, adjusted, _ = _coverage(strata)
        assert adjusted - marginal > 0.05, f"{strata} strata gained {adjusted - marginal:.1%}"
