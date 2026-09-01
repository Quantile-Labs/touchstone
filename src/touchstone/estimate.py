# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Turn item records into estimates, and write them where a reviewer can find them.

A pure function of the records. No container, no daemon, no network, so every number in a
bundle can be recomputed from the bundle years after the run that produced it, by anyone.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from touchstone import __version__
from touchstone.contracts import ItemRecord
from touchstone.contracts.estimates import Calibration, Estimate, Estimates, WorstStratum
from touchstone.errors import EstimateError
from touchstone.freeze import LOCK_NAME, load_lock
from touchstone.run import ITEMS_NAME
from touchstone.stats.bootstrap import BCA_REFERENCE, RESAMPLES, bootstrap_bca

__all__ = ["RESAMPLES"]
from touchstone.stats.calibration import calibration, confident_and_wrong_by_item
from touchstone.stats.proportion import (
    CLUSTERED_REFERENCE,
    WILSON_REFERENCE,
    Z_95,
    bonferroni_z,
    clustered_wilson,
    format_interval,
    interval,
    wilson,
)
from touchstone.stats.replicates import between_replicate
from touchstone.stats.rollup import Cell, by_item, metrics, scores, values, values_by_item

ESTIMATES_NAME = "estimates.json"
CONFIDENT = 0.9
"""Where confident-and-wrong starts. A wrong answer delivered hesitantly can be caught
downstream; one delivered at 0.9 cannot."""


def load_items(path: Path) -> list[ItemRecord]:
    """Read `items.jsonl`, one record per line. A malformed line names itself."""
    if path.is_dir():
        path = path / ITEMS_NAME
    if not path.is_file():
        raise EstimateError(f"no item records at {path}. Run the plan before estimating it")

    items = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(ItemRecord.model_validate_json(line))
        except ValidationError as exc:
            raise EstimateError(f"{path}:{number}: not an item record: {exc}") from exc

    if not items:
        raise EstimateError(f"{path} holds no item records")
    return items


def _proportion(
    metric: str,
    where: Cell,
    cells: list[tuple[int, int]],
    pack_id: str | None = None,
    **parameters: Any,
) -> Estimate:
    """A rate over `cells`, one `(successes, observations)` pair per distinct item.

    Where every item was observed once the rows are the items and the Wilson interval is
    computed straight off the counts, which is what every bundle before this held. Where
    any item was observed more than once the rows are not independent and the interval is
    computed over items instead, through `clustered_wilson`.

    `k` and `n` stay the raw counts either way, because they are what a reader is
    checking against the rows, and `effective_n` records the denominator the interval was
    actually computed at. Every estimate carries it, equal to `n` in the unclustered
    case, so anything recomputing an interval later has one field to read rather than a
    branch to repeat.
    """
    k = sum(successes for successes, _ in cells)
    n = sum(observations for _, observations in cells)
    repeated = any(observations > 1 for _, observations in cells)

    if repeated:
        computed = clustered_wilson(cells)
        point, low, high = computed.point, computed.low, computed.high
        estimator, reference = "wilson_clustered", CLUSTERED_REFERENCE
        extra: dict[str, Any] = {
            "items": len(cells),
            "observations": n,
            "effective_n": computed.effective_n,
            "design_effect": computed.design_effect,
        }
    else:
        point, low, high = wilson(k, n)
        estimator, reference = "wilson", WILSON_REFERENCE
        extra = {"effective_n": float(n)}

    return Estimate(
        metric=metric,
        stratum=dict(where),
        pack_id=pack_id,
        n=n,
        k=k,
        point=point if n else None,
        low=low,
        high=high,
        estimator=estimator,
        parameters={"z": Z_95, "confidence": 0.95, **extra, **parameters},
        reference=reference,
    )


def _mean(
    metric: str,
    where: Cell,
    sample: list[float],
    observations: int,
    seed: int,
    resamples: int,
    pack_id: str | None = None,
) -> Estimate:
    """A mean over `sample`, which is one mean score per distinct item.

    The bootstrap resamples what it is given, so giving it rows would have it draw the
    same item's score twice as though the second draw were new evidence. It is given
    items, and `n` stays the row count so that it means the same thing here as it does on
    a rate, with `effective_n` carrying the denominator the interval was computed over.
    """
    point, low, high = bootstrap_bca(sample, resamples=resamples, seed=seed)
    return Estimate(
        metric=metric,
        stratum=dict(where),
        pack_id=pack_id,
        n=observations,
        k=None,
        point=point,
        low=low,
        high=high,
        estimator="bootstrap_bca",
        parameters={
            "resamples": resamples,
            "seed": seed,
            "confidence": 0.95,
            "items": len(sample),
            "observations": observations,
            "effective_n": float(len(sample)),
        },
        reference=BCA_REFERENCE,
    )


def declared_calibration(run_dir: Path) -> dict[str, str]:
    """What each pack declared its confidence to be a claim about, from the frozen plan.

    Read from the lock the run copied beside its records, so the answer is part of the
    frozen plan a reviewer checks rather than a flag somebody typed. A run directory
    without a lock is a hand-built sample and simply declares nothing.
    """
    path = run_dir / LOCK_NAME
    if not path.is_file():
        return {}
    lock = load_lock(path)
    return {pack.id: pack.calibrates for pack in lock.packs if pack.calibrates}


def _groupings(keys: list[str]) -> list[list[str]]:
    """The rollups a request for `keys` asks for: overall, each key alone, then the cross.

    A score card asks about one dimension at a time. A geographic indicator searches cells
    keyed `zone` and a language indicator cells keyed `language`, so a run given both keys
    and only their crossing holds nothing either one can read, and `grade` refuses them for
    naming a metric that was never computed. Emitting each key's own rollup is what lets a
    single `estimate` serve a card that names several dimensions.

    The crossing is still emitted, because whether a weakness in one dimension is
    concentrated in a cell of another is a real question. It comes last because it is the
    rarer one and the more expensive. A single key asks for the same rollup twice, so it is
    emitted once.
    """
    if len(keys) < 2:
        return [[]] + ([keys] if keys else [])
    return [[]] + [[key] for key in keys] + [keys]


def _estimates_for(
    items: list[ItemRecord],
    groupings: list[list[str]],
    pack_id: str | None,
    seed: int,
    resamples: int,
) -> list[Estimate]:
    computed = []
    for metric in metrics(items):
        for grouping in groupings:
            for where, cells in sorted(by_item(items, metric, grouping).items()):
                computed.append(_proportion(metric, where, cells, pack_id=pack_id))
    for metric in scores(items):
        for grouping in groupings:
            rows = values(items, metric, grouping)
            for where, sample in sorted(values_by_item(items, metric, grouping).items()):
                computed.append(
                    _mean(metric, where, sample, len(rows[where]), seed, resamples, pack_id=pack_id)
                )
    return computed


def _calibrate(
    items: list[ItemRecord],
    metric: str,
    pack_id: str | None,
    confident: float,
) -> tuple[Calibration, Estimate]:
    known = set(metrics(items))
    where = f" for pack {pack_id}" if pack_id else ""
    if metric not in known:
        raise EstimateError(
            f"cannot calibrate {metric!r}{where}: no item reports it as an outcome. "
            f"Outcomes present: {', '.join(sorted(known)) or 'none'}"
        )
    curve = calibration(items, metric)
    if curve.n == 0:
        raise EstimateError(
            f"cannot calibrate {metric!r}{where}: no item carrying it reports a confidence"
        )
    curve.pack_id = pack_id
    cells = confident_and_wrong_by_item(items, metric, confident)
    rate = _proportion(
        f"confident_and_wrong({metric})", (), cells, pack_id=pack_id, threshold=confident
    )
    return curve, rate


def estimate(
    items: list[ItemRecord],
    keys: list[str] | None = None,
    calibrate: list[str] | None = None,
    declared: dict[str, str] | None = None,
    seed: int = 0,
    resamples: int = RESAMPLES,
    confident: float = CONFIDENT,
) -> Estimates:
    """Every outcome and score, overall and once per cell of the requested strata.

    Booleans become rates with a Wilson interval, continuous scores become means with a
    BCa interval, and each carries the denominator it was computed over.

    Several keys are rolled up one at a time as well as crossed, so a card naming one
    dimension per indicator reads its cells off a single run. See `_groupings`.

    Where more than one pack contributed, every metric is also computed per pack. Two
    packs both reporting `correct` are not measuring the same thing, so the pooled figure
    is kept but marked, and the per-pack figures are what a reader should quote.

    `declared` is what each pack said its confidence is a claim about, read from the
    frozen plan. `calibrate` overrides it for every pack, which is what re-analysing an
    old bundle under a corrected definition needs.
    """
    keys = list(keys or [])
    declared = dict(declared or {})
    groupings = _groupings(keys)

    packs = sorted({item.pack_id for item in items if item.pack_id is not None})
    pooled = len(packs) > 1
    sole = packs[0] if len(packs) == 1 else None

    computed = _estimates_for(items, groupings, sole, seed, resamples)
    curves = []

    for metric in calibrate or []:
        curve, rate = _calibrate(items, metric, sole, confident)
        curves.append(curve)
        computed.append(rate)

    for pack in packs if pooled else []:
        subset = [item for item in items if item.pack_id == pack]
        computed.extend(_estimates_for(subset, groupings, pack, seed, resamples))

    if not calibrate:
        for pack in packs:
            outcome = declared.get(pack)
            if outcome is None:
                continue
            subset = [item for item in items if item.pack_id == pack]
            curve, rate = _calibrate(subset, outcome, pack, confident)
            curves.append(curve)
            computed.append(rate)

    spreads = []
    for scope, subset in [(sole, items)] + [
        (pack, [item for item in items if item.pack_id == pack])
        for pack in (packs if pooled else [])
    ]:
        for metric in metrics(subset):
            spread = between_replicate(subset, metric)
            if len(spread.rates) > 1:
                spread.pack_id = scope
                spreads.append(spread)

    return Estimates(
        touchstone_version=__version__,
        items=len(items),
        grouped_by=keys,
        packs=packs,
        pooled=pooled,
        estimates=computed,
        calibration=curves,
        replicate_variance=spreads,
    )


def _adjusted_for_selection(entry: Estimate, comparisons: int) -> Estimate:
    """The selected cell, with an interval that holds over every cell it beat.

    Ranking cells and reporting the minimum selects on the noise, so the marginal interval
    on the winner undercovers, and not slightly: over ten equal cells of 180 a nominal 95
    percent Wilson interval holds about 69 percent of the time, and roughly a third of the
    time it sits entirely below the true rate, which reads as a confident finding of a
    weak group that is not weak. A Bonferroni quantile over the cells that were ranked
    restores the coverage.

    The point estimate is left as the selected minimum and is still biased low. Widening
    the interval makes the estimate admit that rather than correct it, which is the
    honest half of the fix and the half that does not need a prior.
    """
    if entry.k is None or entry.point is None:
        raise EstimateError(
            f"cannot adjust {entry.metric!r} for selection: the cell carries no counts. "
            "A selected minimum reported with an unadjusted interval is the error this "
            "function exists to prevent, so it is refused rather than printed"
        )
    z = bonferroni_z(comparisons)
    effective = entry.parameters.get("effective_n", entry.n)
    low, high = interval(entry.point, float(effective), z)
    return entry.model_copy(
        update={
            "low": low,
            "high": high,
            "parameters": {
                **entry.parameters,
                "z": z,
                "adjustment": "bonferroni",
                "selected_from": comparisons,
            },
        }
    )


def worst_stratum(
    estimates: Estimates,
    metric: str,
    min_n: int = 30,
    higher_is_better: bool = True,
) -> WorstStratum:
    """The weakest cell of the rollup for one metric, among cells of at least `min_n`.

    `min_n` is the whole point of the indicator. Without it the worst stratum is whichever
    cell happened to hold three items, and the headline reports noise. Cells are ranked on
    the point estimate and ties break on the stratum key, so the answer does not depend on
    dictionary order.
    """
    if min_n < 1:
        raise EstimateError(f"min_n has to be at least 1, got {min_n}")

    cells = [entry for entry in estimates.estimates if entry.metric == metric and entry.stratum]
    ranked = [
        (entry.point, sorted(entry.stratum.items()), entry)
        for entry in cells
        if entry.n >= min_n and entry.point is not None
    ]
    excluded = [entry for entry in cells if entry.n < min_n]

    worst = None
    if ranked:
        sign = 1.0 if higher_is_better else -1.0
        _, _, selected = min(ranked, key=lambda row: (sign * row[0], row[1]))
        worst = _adjusted_for_selection(selected, len(ranked))

    return WorstStratum(
        metric=metric,
        min_n=min_n,
        higher_is_better=higher_is_better,
        worst=worst,
        excluded=sorted(excluded, key=lambda entry: sorted(entry.stratum.items())),
        selected_from=len(ranked),
    )


def write_estimates(estimates: Estimates, out_dir: Path) -> Path:
    path = out_dir / ESTIMATES_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(estimates.model_dump(), indent=2, sort_keys=True) + "\n")
    return path


def _where(entry: Estimate) -> str:
    parts = [f"{key}={value}" for key, value in sorted(entry.stratum.items())]
    if entry.pack_id:
        parts.insert(0, entry.pack_id)
    return ", ".join(parts) if parts else "overall"


def lines(estimates: Estimates) -> list[str]:
    """One printed line per estimate. Never a rate without its interval and denominator."""
    rendered = []
    for entry in estimates.estimates:
        if entry.k is not None:
            # The stored interval, not a fresh one off k and n. Once an interval can be
            # widened for clustering or for selection, recomputing it here would print a
            # number the bundle does not contain.
            body = (
                format_interval(entry.point, entry.low, entry.high, entry.n)
                if entry.point is not None
                else "undefined (n=0)"
            )
        else:
            body = (
                f"{entry.point:.3f} (95% CI {entry.low:.3f}-{entry.high:.3f}, n={entry.n}, "
                f"{entry.estimator})"
            )
        rendered.append(f"  {entry.metric} [{_where(entry)}]: {body}")

    for curve in estimates.calibration:
        scope = f"{curve.pack_id} " if curve.pack_id else ""
        rendered.append(
            f"  {scope}{curve.metric} calibration: ECE {curve.ece:.3f} over n={curve.n}"
        )
    for spread in estimates.replicate_variance:
        scope = f"{spread.pack_id} " if spread.pack_id else ""
        rendered.append(
            f"  {scope}{spread.metric} across {len(spread.rates)} replicate(s): "
            f"spread {spread.spread:.3f}, {spread.unstable_items} of "
            f"{spread.repeated_items} item(s) unstable"
        )
        if spread.components is not None:
            parts = spread.components
            rendered.append(
                f"  {scope}{spread.metric} variance over {parts.items} item(s) at "
                f"{parts.trials:g} trial(s): completion {parts.completion:.5f}, "
                f"item {parts.item:.5f}, total {parts.total:.5f}"
            )
    return rendered
