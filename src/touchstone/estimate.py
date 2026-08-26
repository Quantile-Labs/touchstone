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
from touchstone.stats.calibration import calibration, confident_and_wrong
from touchstone.stats.proportion import (
    WILSON_REFERENCE,
    Z_95,
    bonferroni_z,
    format_rate,
    wilson,
)
from touchstone.stats.replicates import between_replicate
from touchstone.stats.rollup import Cell, metrics, scores, tally, values

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
    metric: str, where: Cell, k: int, n: int, pack_id: str | None = None, **parameters: Any
) -> Estimate:
    point, low, high = wilson(k, n)
    return Estimate(
        metric=metric,
        stratum=dict(where),
        pack_id=pack_id,
        n=n,
        k=k,
        point=point if n else None,
        low=low,
        high=high,
        estimator="wilson",
        parameters={"z": Z_95, "confidence": 0.95, **parameters},
        reference=WILSON_REFERENCE,
    )


def _mean(
    metric: str,
    where: Cell,
    sample: list[float],
    seed: int,
    resamples: int,
    pack_id: str | None = None,
) -> Estimate:
    point, low, high = bootstrap_bca(sample, resamples=resamples, seed=seed)
    return Estimate(
        metric=metric,
        stratum=dict(where),
        pack_id=pack_id,
        n=len(sample),
        k=None,
        point=point,
        low=low,
        high=high,
        estimator="bootstrap_bca",
        parameters={"resamples": resamples, "seed": seed, "confidence": 0.95},
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
            for where, (k, n) in sorted(tally(items, metric, grouping).items()):
                computed.append(_proportion(metric, where, k, n, pack_id=pack_id))
    for metric in scores(items):
        for grouping in groupings:
            for where, sample in sorted(values(items, metric, grouping).items()):
                computed.append(_mean(metric, where, sample, seed, resamples, pack_id=pack_id))
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
    wrong, scored = confident_and_wrong(items, metric, confident)
    rate = _proportion(
        f"confident_and_wrong({metric})", (), wrong, scored, pack_id=pack_id, threshold=confident
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

    Where more than one pack contributed, every metric is also computed per pack. Two
    packs both reporting `correct` are not measuring the same thing, so the pooled figure
    is kept but marked, and the per-pack figures are what a reader should quote.

    `declared` is what each pack said its confidence is a claim about, read from the
    frozen plan. `calibrate` overrides it for every pack, which is what re-analysing an
    old bundle under a corrected definition needs.
    """
    keys = list(keys or [])
    declared = dict(declared or {})
    groupings: list[list[str]] = [[]] + ([keys] if keys else [])

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
    if entry.k is None:
        raise EstimateError(
            f"cannot adjust {entry.metric!r} for selection: the cell carries no counts. "
            "A selected minimum reported with an unadjusted interval is the error this "
            "function exists to prevent, so it is refused rather than printed"
        )
    z = bonferroni_z(comparisons)
    _, low, high = wilson(entry.k, entry.n, z=z)
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
            body = format_rate(entry.k, entry.n)
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
    return rendered
