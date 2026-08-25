"""Group item records into cells and count what happened in each.

The strata are open dimensions, declared by the pack rather than by this engine, so the
rollup never names a key. It takes the keys it is asked for and reports the cells it
finds, carrying `n` into every one of them: a cell without its denominator is how a
three-item result becomes a headline.
"""

from collections import Counter
from collections.abc import Iterable

from touchstone.contracts import ItemRecord

Cell = tuple[tuple[str, str], ...]
"""A stratum as a sorted, hashable key. The empty tuple is the whole sample."""

OVERALL: Cell = ()


def cell(item: ItemRecord, keys: Iterable[str]) -> Cell:
    """The cell an item falls into. An item missing a requested key is `(unset)` there,
    because dropping it would silently shrink the denominator."""
    return tuple((key, item.stratum.get(key, "(unset)")) for key in keys)


def metrics(items: Iterable[ItemRecord]) -> list[str]:
    """Every outcome key any item reports, sorted. Packs are not required to agree."""
    seen: set[str] = set()
    for item in items:
        seen.update(item.outcome)
    return sorted(seen)


def tally(
    items: Iterable[ItemRecord], metric: str, keys: Iterable[str] = ()
) -> dict[Cell, tuple[int, int]]:
    """Count (successes, observations) per cell for one boolean outcome.

    An item that does not report `metric` is not in that metric's denominator. It was not
    observed, and counting it as a failure would be an invention.
    """
    keys = list(keys)
    successes: Counter[Cell] = Counter()
    observations: Counter[Cell] = Counter()
    for item in items:
        if metric not in item.outcome:
            continue
        where = cell(item, keys)
        observations[where] += 1
        successes[where] += int(item.outcome[metric])
    return {where: (successes[where], count) for where, count in observations.items()}


def scores(items: Iterable[ItemRecord]) -> list[str]:
    """Every continuous score key any item reports, sorted."""
    seen: set[str] = set()
    for item in items:
        seen.update(item.score)
    return sorted(seen)


def values(
    items: Iterable[ItemRecord], metric: str, keys: Iterable[str] = ()
) -> dict[Cell, list[float]]:
    """The raw sample per cell for one continuous score, in the order it was observed.

    Raw rather than summarised, because the bootstrap resamples the sample itself.
    """
    keys = list(keys)
    collected: dict[Cell, list[float]] = {}
    for item in items:
        if metric not in item.score:
            continue
        collected.setdefault(cell(item, keys), []).append(item.score[metric])
    return collected
