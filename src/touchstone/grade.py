"""Apply a score card to the estimates and say what may be claimed.

Pure function of `estimates.json` and the frozen plan, like `estimate` before it, so a
grade can be recomputed from a sealed bundle years later and a corrected score card can be
replayed against an old run without rerunning anything.

The whole module exists for one behaviour ASQI has no way to express. A rule that awards a
level when a rate clears a threshold is a claim about the rate, and a rate is an estimate.
Where the interval straddles the threshold, the evidence does not say which side of the
boundary the system is on, and the answer is neither the better level nor quietly the
worse one. It is `indeterminate`, reported with the two levels it lies between.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from touchstone import __version__, expressions
from touchstone import estimate as estimate_items
from touchstone.contracts.estimates import Estimate, Estimates
from touchstone.contracts.scorecard import (
    INTERVAL_CONDITIONS,
    INTERVAL_SOURCES,
    Expression,
    GradedIndicator,
    Indicator,
    Measured,
    MetricRef,
    Rule,
    ScoreCard,
    Scorecard,
    Verdict,
)
from touchstone.errors import ScoreCardError
from touchstone.estimate import ESTIMATES_NAME
from touchstone.freeze import HASH_NAME, LOCK_NAME, load_lock

SCORECARD_NAME = "scorecard.json"

AWARDED = "awarded"
REFUSED = "refused"
INDETERMINATE = "indeterminate"


def load_scorecard(path: Path) -> ScoreCard:
    """Read a score card and check it against itself. Raises on anything malformed."""
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ScoreCardError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScoreCardError(f"{path} is not a score card")
    try:
        return ScoreCard.model_validate(raw)
    except ValidationError as exc:
        raise ScoreCardError(f"{path}: {exc}") from exc


def grade(
    score_card: ScoreCard,
    estimates: Estimates,
    access_tier: str,
    summary_only: frozenset[str] = frozenset(),
    plan_sha256: str | None = None,
) -> Scorecard:
    """Every indicator, decided against the estimates and capped by the access tier."""
    ceiling = _tier_ceiling(score_card, access_tier)
    graded = [
        _indicator(indicator, score_card, estimates, ceiling, summary_only)
        for indicator in score_card.indicators
    ]
    return Scorecard(
        touchstone_version=__version__,
        score_card_name=score_card.score_card_name,
        access_tier=access_tier,
        levels=list(score_card.levels),
        plan_sha256=plan_sha256,
        indicators=graded,
    )


def _tier_ceiling(score_card: ScoreCard, access_tier: str) -> str | None:
    """The best level this tier may reach, or None where the score card leaves it open."""
    if not score_card.tier_ceilings:
        return None
    if access_tier not in score_card.tier_ceilings:
        known = ", ".join(sorted(score_card.tier_ceilings))
        raise ScoreCardError(
            f"the plan declares access tier {access_tier!r} and the score card sets no "
            f"ceiling for it. Tiers with a ceiling: {known}. Refusing rather than grading "
            "an unrecognised tier as though it were unrestricted"
        )
    return score_card.tier_ceilings[access_tier]


def _indicator(
    indicator: Indicator,
    score_card: ScoreCard,
    estimates: Estimates,
    ceiling: str | None,
    summary_only: frozenset[str],
) -> GradedIndicator:
    measured, expression = _measure(indicator, estimates, summary_only)
    value, low, high = _value_of(indicator.metric, measured)
    applied = _applied_ceiling(score_card, ceiling, measured)

    if value is None:
        return GradedIndicator(
            id=indicator.id,
            name=indicator.name,
            verdict="ungraded",
            reason=_nothing_measured(measured),
            measured=measured,
            expression=expression,
        )

    decided = _walk(indicator.assessment, value, low, high)
    return _cap(indicator, decided, score_card, applied, measured, expression)


@dataclass(frozen=True)
class _Decision:
    """What the ladder concluded, before any ceiling and before it is given an identity."""

    verdict: Verdict
    level: str | None = None
    rule: Rule | None = None
    between: tuple[str, ...] = ()
    reason: str | None = None


def _walk(assessment: list[Rule], value: float, low: float | None, high: float | None) -> _Decision:
    """The ladder, top down. The first rule that holds decides; the first whose boundary
    the interval straddles stops the descent and takes the levels below it as the floor."""
    straddled: Rule | None = None
    for rule in assessment:
        outcome = _decide(rule, value, low, high)
        if outcome == AWARDED:
            if straddled is None:
                return _Decision(verdict="graded", level=rule.level, rule=rule)
            return _Decision(
                verdict="indeterminate",
                rule=straddled,
                between=(straddled.level, rule.level),
                reason=(
                    f"the interval spans the {straddled.level} boundary of "
                    f"{straddled.threshold:g}, so the grade is {straddled.level} or "
                    f"{rule.level} and the evidence does not say which"
                ),
            )
        if outcome == INDETERMINATE and straddled is None:
            straddled = rule

    if straddled is not None:
        return _Decision(
            verdict="indeterminate",
            rule=straddled,
            between=(straddled.level,),
            reason=(
                f"the interval spans the {straddled.level} boundary of "
                f"{straddled.threshold:g}, and no lower rule holds, so the grade is "
                f"{straddled.level} or no grade at all"
            ),
        )
    return _Decision(verdict="ungraded", reason="no rule in the score card holds for this value")


def _decide(rule: Rule, value: float, low: float | None, high: float | None) -> str:
    """`awarded`, `refused`, or `indeterminate` for one rung.

    The three interval conditions are the reason this function is not a dictionary of
    comparisons. `greater_equal_ci_lower` awards only when the whole interval clears the
    threshold, refuses only when the whole interval sits below it, and reports the overlap
    as what it is rather than resolving it in either direction.
    """
    threshold = rule.threshold

    if rule.condition == "greater_equal_ci_lower":
        if low is None or high is None:
            raise ScoreCardError(f"{rule.condition} needs an interval and this metric has none")
        if low >= threshold:
            return AWARDED
        return REFUSED if high < threshold else INDETERMINATE

    if rule.condition == "less_equal_ci_upper":
        if low is None or high is None:
            raise ScoreCardError(f"{rule.condition} needs an interval and this metric has none")
        if high <= threshold:
            return AWARDED
        return REFUSED if low > threshold else INDETERMINATE

    if rule.condition == "threshold_crossed_by_interval":
        if low is None or high is None:
            raise ScoreCardError(f"{rule.condition} needs an interval and this metric has none")
        return AWARDED if low <= threshold <= high else REFUSED

    held = {
        "greater_equal": value >= threshold,
        "greater_than": value > threshold,
        "less_equal": value <= threshold,
        "less_than": value < threshold,
        "equal_to": value == threshold,
    }[rule.condition]
    return AWARDED if held else REFUSED


def _cap(
    indicator: Indicator,
    decided: _Decision,
    score_card: ScoreCard,
    ceiling: tuple[str | None, str | None],
    measured: list[Measured],
    expression: str | None,
) -> GradedIndicator:
    """Apply the claim ceiling and give the decision its identity.

    A ceiling below the whole indeterminate range settles it: if the grade could not have
    exceeded the ceiling either way, the range collapses and the interval decides nothing.
    """
    level, reason = ceiling
    built = GradedIndicator(
        id=indicator.id,
        name=indicator.name,
        verdict=decided.verdict,
        level=decided.level,
        rule=decided.rule,
        between=list(decided.between),
        reason=decided.reason,
        uncapped_level=decided.level,
        measured=measured,
        expression=expression,
    )
    if level is None:
        return built

    if decided.verdict == "graded" and decided.level is not None:
        capped = _worst_of(score_card, decided.level, level)
        if capped == decided.level:
            return built
        return built.model_copy(
            update={"level": capped, "ceiling": level, "ceiling_reason": reason}
        )

    if decided.verdict == "indeterminate" and decided.between:
        narrowed = [_worst_of(score_card, each, level) for each in decided.between]
        if len(set(narrowed)) == 1 and len(decided.between) > 1:
            return built.model_copy(
                update={
                    "verdict": "graded",
                    "level": narrowed[0],
                    "uncapped_level": decided.between[0],
                    "ceiling": level,
                    "ceiling_reason": reason,
                    "between": [],
                    "reason": (
                        f"{reason} caps this at {level}, which is at or below both ends of "
                        f"{' to '.join(decided.between)}, so the interval no longer decides "
                        "anything"
                    ),
                }
            )
        return built.model_copy(
            update={"between": narrowed, "ceiling": level, "ceiling_reason": reason}
        )

    return built


def _worst_of(score_card: ScoreCard, left: str, right: str) -> str:
    return left if score_card.rank(left) >= score_card.rank(right) else right


def _worse(score_card: ScoreCard, left: str | None, right: str | None) -> str | None:
    if left is None:
        return right
    if right is None:
        return left
    return _worst_of(score_card, left, right)


def _applied_ceiling(
    score_card: ScoreCard, tier_ceiling: str | None, measured: list[Measured]
) -> tuple[str | None, str | None]:
    """The ceiling that actually binds, and which rule set it."""
    summary = score_card.summary_only_ceiling if any(one.summary_only for one in measured) else None
    if summary is None:
        return (tier_ceiling, "access_tier" if tier_ceiling else None)
    if tier_ceiling is None:
        return (summary, "summary_only")
    binding = _worst_of(score_card, tier_ceiling, summary)
    return (binding, "access_tier" if binding == tier_ceiling else "summary_only")


def _measure(
    indicator: Indicator, estimates: Estimates, summary_only: frozenset[str]
) -> tuple[list[Measured], str | None]:
    if isinstance(indicator.metric, Expression):
        measured = [
            _resolve(ref, estimates, summary_only, indicator.id)
            for ref in indicator.metric.values.values()
        ]
        return measured, indicator.metric.expression
    return [_resolve(indicator.metric, estimates, summary_only, indicator.id)], None


def _value_of(
    metric: MetricRef | Expression, measured: list[Measured]
) -> tuple[float | None, float | None, float | None]:
    """The number the ladder is walked against, with its interval where one survives.

    An expression returns no interval. Combining two of them needs the correlation between
    the estimates and the bundle does not record it, so the alternative is an interval that
    looks like evidence and is not."""
    if isinstance(metric, MetricRef):
        one = measured[0]
        return one.value, one.low, one.high

    values = {}
    for name, ref in metric.values.items():
        one = _matching(measured, ref)
        if one.value is None:
            return None, None, None
        values[name] = one.value
    return expressions.evaluate(metric.expression, values), None, None


def _matching(measured: list[Measured], ref: MetricRef) -> Measured:
    return next(one for one in measured if one.ref == ref)


def _nothing_measured(measured: list[Measured]) -> str:
    empty = [one for one in measured if one.value is None]
    if not empty:
        return "the metric could not be evaluated"
    where = ", ".join(sorted({one.ref.name for one in empty}))
    if all(one.n == 0 for one in empty):
        return f"no observations for {where}, so there is nothing to grade"
    return f"{where} has a denominator but no point estimate"


def _resolve(
    ref: MetricRef, estimates: Estimates, summary_only: frozenset[str], indicator_id: str
) -> Measured:
    """Find the number an indicator names. A miss is a hard error, never a zero.

    ASQI validates the id pattern on a test definition and not on the score card filter
    that references one, so a score card there can name a test that never ran and the
    indicator quietly scores nothing. See 01-ASQI-TEARDOWN.md section 4, defect 3.
    """
    if ref.pack_id is None and estimates.pooled:
        raise ScoreCardError(
            f"{indicator_id}: {ref.name!r} names no pack and {len(estimates.packs)} packs "
            f"contributed ({', '.join(estimates.packs)}). The pooled figure adds "
            "denominators from packs that are not measuring the same thing. Name a pack"
        )
    if ref.pack_id is not None and ref.pack_id not in estimates.packs:
        known = ", ".join(estimates.packs) or "none"
        raise ScoreCardError(
            f"{indicator_id}: no pack {ref.pack_id!r} in this bundle. Packs that ran: {known}"
        )

    contaminated = bool(
        summary_only & (frozenset({ref.pack_id}) if ref.pack_id else frozenset(estimates.packs))
    )

    if ref.source == "calibration":
        for curve in estimates.calibration:
            if curve.metric == ref.name and curve.pack_id == ref.pack_id:
                return Measured(ref=ref, value=curve.ece, n=curve.n, summary_only=contaminated)
        raise ScoreCardError(_missing(indicator_id, ref, "calibration"))

    if ref.source == "replicate_variance":
        for spread in estimates.replicate_variance:
            if spread.metric == ref.name and spread.pack_id == ref.pack_id:
                observed = sum(total for _, total in spread.rates.values())
                return Measured(ref=ref, value=spread.spread, n=observed, summary_only=contaminated)
        raise ScoreCardError(_missing(indicator_id, ref, "replicate_variance"))

    if ref.source == "worst_stratum":
        return _worst(ref, estimates, contaminated, indicator_id)

    for entry in estimates.estimates:
        if (
            entry.metric == ref.name
            and entry.pack_id == ref.pack_id
            and entry.stratum == ref.stratum
        ):
            return _from_estimate(ref, entry, contaminated)
    raise ScoreCardError(_missing(indicator_id, ref, "estimate"))


def _worst(ref: MetricRef, estimates: Estimates, contaminated: bool, indicator_id: str) -> Measured:
    """The weakest cell of the rollup, through the same function `estimate` uses."""
    subset = estimates.model_copy(
        update={
            "estimates": [entry for entry in estimates.estimates if entry.pack_id == ref.pack_id]
        }
    )
    found = estimate_items.worst_stratum(
        subset, ref.name, min_n=ref.min_n, higher_is_better=ref.higher_is_better
    )
    if found.worst is None:
        thin = len(found.excluded)
        raise ScoreCardError(
            f"{indicator_id}: no stratum of {ref.name!r} reaches n={ref.min_n} "
            f"({thin} cell(s) below it). A worst stratum computed over cells this thin is "
            "noise, and reporting one would be worse than reporting none"
        )
    return _from_estimate(ref, found.worst, contaminated)


def _from_estimate(ref: MetricRef, entry: Estimate, contaminated: bool) -> Measured:
    interval = ref.source in INTERVAL_SOURCES and entry.point is not None
    return Measured(
        ref=ref,
        value=entry.point,
        low=entry.low if interval else None,
        high=entry.high if interval else None,
        n=entry.n,
        stratum=dict(entry.stratum),
        summary_only=contaminated,
    )


def _missing(indicator_id: str, ref: MetricRef, kind: str) -> str:
    where = f", stratum {ref.stratum}" if ref.stratum else ""
    pack = f" for pack {ref.pack_id!r}" if ref.pack_id else " pooled"
    return (
        f"{indicator_id}: no {kind} named {ref.name!r}{pack}{where} in this bundle. "
        "An indicator naming a metric that was never computed is an error, not a zero"
    )


def check(score_card: ScoreCard, estimates: Estimates) -> list[str]:
    """Cross-check a score card against a bundle. Returns every problem, not the first.

    Run before anything is graded, so a score card with four broken references reports
    four rather than one per attempt.
    """
    problems = []
    for indicator in score_card.indicators:
        metric = indicator.metric
        has_interval = isinstance(metric, MetricRef) and metric.source in INTERVAL_SOURCES

        for rule in indicator.assessment:
            if rule.condition in INTERVAL_CONDITIONS and not has_interval:
                carries = (
                    "an expression, which carries no interval by design"
                    if isinstance(metric, Expression)
                    else f"source {metric.source!r}, which carries no interval"
                )
                problems.append(
                    f"{indicator.id}: rule {rule.level} uses {rule.condition} against {carries}"
                )

        if isinstance(metric, Expression):
            used = expressions.names(metric.expression)
            declared = set(metric.values)
            for name in sorted(used - declared):
                problems.append(f"{indicator.id}: {name!r} is in the expression and not in values")
            for name in sorted(declared - used):
                problems.append(f"{indicator.id}: {name!r} is in values and not in the expression")

        for ref in metric.values.values() if isinstance(metric, Expression) else [metric]:
            try:
                _resolve(ref, estimates, frozenset(), indicator.id)
            except ScoreCardError as exc:
                problems.append(str(exc))
    return problems


def summary_only_packs(run_dir: Path) -> frozenset[str]:
    """Packs the frozen plan records as emitting no items. Empty where there is no lock."""
    path = run_dir / LOCK_NAME
    if not path.exists():
        return frozenset()
    return frozenset(pack.id for pack in load_lock(path).packs if not pack.emits_items)


def access_tier(run_dir: Path) -> str:
    """The tier the plan was frozen with. Not a flag: a grade names the tier it was capped by."""
    path = run_dir / LOCK_NAME
    if not path.exists():
        raise ScoreCardError(
            f"{run_dir} holds no {LOCK_NAME}, so the access tier the run was frozen with is "
            "unknown. A grade without its tier is a claim without its ceiling"
        )
    return load_lock(path).access_tier


def load_estimates(run_dir: Path) -> Estimates:
    """Read `estimates.json` from a run directory."""
    path = run_dir / ESTIMATES_NAME
    if not path.exists():
        raise ScoreCardError(f"{path} does not exist. Run `touchstone estimate` first")
    try:
        return Estimates.model_validate(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ScoreCardError(f"{path}: {exc}") from exc


def plan_hash(run_dir: Path) -> str | None:
    """The frozen plan's hash, as `freeze` wrote it beside the lock."""
    path = run_dir / HASH_NAME
    if not path.exists():
        return None
    return path.read_text().split()[0]


def write_scorecard(scorecard: Scorecard, out_dir: Path) -> Path:
    path = out_dir / SCORECARD_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scorecard.model_dump(), indent=2, sort_keys=True) + "\n")
    return path


def lines(scorecard: Scorecard) -> list[str]:
    """One printed line per indicator, and never a level without what qualified it."""
    rendered = []
    for indicator in scorecard.indicators:
        head = f"{indicator.id}: "
        if indicator.verdict == "graded" and indicator.level is not None:
            head += indicator.level
            if indicator.ceiling_reason:
                head += f" (capped from {indicator.uncapped_level} by {indicator.ceiling_reason})"
        elif indicator.verdict == "indeterminate":
            head += f"indeterminate, {' or '.join(indicator.between)}"
        else:
            head += "ungraded"

        shown = indicator.measured[0] if indicator.measured else None
        if shown is not None and shown.value is not None:
            head += f"  [{shown.value:.4g}"
            if shown.low is not None and shown.high is not None:
                head += f", {shown.low:.4g} to {shown.high:.4g}"
            head += f", n={shown.n}"
            if shown.stratum:
                head += ", " + ", ".join(
                    f"{key}={value}" for key, value in sorted(shown.stratum.items())
                )
            head += "]"
        rendered.append(head)
        if indicator.reason:
            rendered.append(f"    {indicator.reason}")
    return rendered
