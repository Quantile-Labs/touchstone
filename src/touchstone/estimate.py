"""Turn item records into estimates, and write them where a reviewer can find them.

A pure function of the records. No container, no daemon, no network, so every number in a
bundle can be recomputed from the bundle years after the run that produced it, by anyone.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from touchstone import __version__
from touchstone.contracts import ItemRecord
from touchstone.contracts.estimates import Estimate, Estimates, WorstStratum
from touchstone.errors import EstimateError
from touchstone.run import ITEMS_NAME
from touchstone.stats.bootstrap import BCA_REFERENCE, RESAMPLES, bootstrap_bca

__all__ = ["RESAMPLES"]
from touchstone.stats.calibration import calibration, confident_and_wrong
from touchstone.stats.proportion import WILSON_REFERENCE, Z_95, format_rate, wilson
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


def _proportion(metric: str, where: Cell, k: int, n: int, **parameters) -> Estimate:
    point, low, high = wilson(k, n)
    return Estimate(
        metric=metric,
        stratum=dict(where),
        n=n,
        k=k,
        point=point if n else None,
        low=low,
        high=high,
        estimator="wilson",
        parameters={"z": Z_95, "confidence": 0.95, **parameters},
        reference=WILSON_REFERENCE,
    )


def _mean(metric: str, where: Cell, sample: list[float], seed: int, resamples: int) -> Estimate:
    point, low, high = bootstrap_bca(sample, resamples=resamples, seed=seed)
    return Estimate(
        metric=metric,
        stratum=dict(where),
        n=len(sample),
        k=None,
        point=point,
        low=low,
        high=high,
        estimator="bootstrap_bca",
        parameters={"resamples": resamples, "seed": seed, "confidence": 0.95},
        reference=BCA_REFERENCE,
    )


def estimate(
    items: list[ItemRecord],
    keys: list[str] | None = None,
    calibrate: list[str] | None = None,
    seed: int = 0,
    resamples: int = RESAMPLES,
    confident: float = CONFIDENT,
) -> Estimates:
    """Every outcome and score, overall and once per cell of the requested strata.

    Booleans become rates with a Wilson interval, continuous scores become means with a
    BCa interval, and each carries the denominator it was computed over.

    `calibrate` names the outcomes a confidence is a claim about, and nothing is
    calibrated unless it is asked for. A stated confidence is a claim about whether the
    answer is right, so binning it against an unrelated boolean produces an ECE that
    reads as authoritative and means nothing. The engine cannot tell which outcome is the
    one, so the caller says.
    """
    keys = list(keys or [])
    groupings: list[list[str]] = [[]] + ([keys] if keys else [])
    computed = []

    for metric in metrics(items):
        for grouping in groupings:
            for where, (k, n) in sorted(tally(items, metric, grouping).items()):
                computed.append(_proportion(metric, where, k, n))

    for metric in scores(items):
        for grouping in groupings:
            for where, sample in sorted(values(items, metric, grouping).items()):
                computed.append(_mean(metric, where, sample, seed, resamples))

    known = set(metrics(items))
    curves = []
    for metric in calibrate or []:
        if metric not in known:
            raise EstimateError(
                f"cannot calibrate {metric!r}: no item reports it as an outcome. "
                f"Outcomes present: {', '.join(sorted(known)) or 'none'}"
            )
        curve = calibration(items, metric)
        if curve.n == 0:
            raise EstimateError(
                f"cannot calibrate {metric!r}: no item carrying it reports a confidence"
            )
        curves.append(curve)
        wrong, scored = confident_and_wrong(items, metric, confident)
        computed.append(
            _proportion(f"confident_and_wrong({metric})", (), wrong, scored, threshold=confident)
        )

    spreads = [between_replicate(items, metric) for metric in metrics(items)]
    spreads = [spread for spread in spreads if len(spread.rates) > 1]

    return Estimates(
        touchstone_version=__version__,
        items=len(items),
        grouped_by=keys,
        estimates=computed,
        calibration=curves,
        replicate_variance=spreads,
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
    eligible = [entry for entry in cells if entry.n >= min_n and entry.point is not None]
    excluded = [entry for entry in cells if entry.n < min_n]

    worst = None
    if eligible:
        worst = min(
            eligible,
            key=lambda entry: (
                entry.point if higher_is_better else -entry.point,
                sorted(entry.stratum.items()),
            ),
        )

    return WorstStratum(
        metric=metric,
        min_n=min_n,
        higher_is_better=higher_is_better,
        worst=worst,
        excluded=sorted(excluded, key=lambda entry: sorted(entry.stratum.items())),
    )


def write_estimates(estimates: Estimates, out_dir: Path) -> Path:
    path = out_dir / ESTIMATES_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(estimates.model_dump(), indent=2, sort_keys=True) + "\n")
    return path


def _where(entry: Estimate) -> str:
    if not entry.stratum:
        return "overall"
    return ", ".join(f"{key}={value}" for key, value in sorted(entry.stratum.items()))


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
        rendered.append(f"  {curve.metric} calibration: ECE {curve.ece:.3f} over n={curve.n}")
    for spread in estimates.replicate_variance:
        rendered.append(
            f"  {spread.metric} across {len(spread.rates)} replicate(s): "
            f"spread {spread.spread:.3f}, {spread.unstable_items} of "
            f"{spread.repeated_items} item(s) unstable"
        )
    return rendered
