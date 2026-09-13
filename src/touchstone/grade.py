# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

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
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Literal

import yaml
from pydantic import ValidationError

from touchstone import __version__, expressions, positions
from touchstone import estimate as estimate_items
from touchstone.bundle import sha256_file
from touchstone.contracts import ItemRecord
from touchstone.contracts.audit import AUDIT_NAME, AuditResponse, AuditResponses
from touchstone.contracts.diagnostics import Problem
from touchstone.contracts.estimates import Estimate, Estimates
from touchstone.contracts.scorecard import (
    INTERVAL_CONDITIONS,
    INTERVAL_SOURCES,
    AuditRef,
    Difference,
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
from touchstone.run import ITEMS_NAME
from touchstone.stats import paired
from touchstone.stats.proportion import Z_95

SCORECARD_NAME = "scorecard.json"

AWARDED = "awarded"
REFUSED = "refused"
INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class Prior:
    """The evaluation before this one, for the indicators that grade movement."""

    estimates: Estimates
    summary_only: frozenset[str] = frozenset()
    plan_sha256: str | None = None
    items: list[ItemRecord] | None = None
    """None where the earlier bundle holds no items.jsonl, which leaves a paired difference
    nothing to join and sends it to the unpaired comparison."""


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
    audit: AuditResponses | None = None,
    audit_sha256: str | None = None,
    prior: Prior | None = None,
    items: list[ItemRecord] | None = None,
) -> Scorecard:
    """Every indicator, decided against the estimates and capped by the access tier.

    `items` is this bundle's records, read only by a paired difference, which joins them on
    `item_id` against the prior bundle's.
    """
    graded = [
        _indicator(
            indicator,
            score_card,
            estimates,
            access_tier,
            summary_only,
            audit,
            prior,
            items,
            plan_sha256,
        )
        for indicator in score_card.indicators
    ]
    return Scorecard(
        touchstone_version=__version__,
        score_card_name=score_card.score_card_name,
        access_tier=access_tier,
        levels=list(score_card.levels),
        plan_sha256=plan_sha256,
        prior_plan_sha256=prior.plan_sha256 if prior else None,
        audit_name=audit.audit_name if audit else None,
        audit_assessor=audit.assessor if audit else None,
        audit_sha256=audit_sha256,
        indicators=graded,
    )


NOT_ASSESSABLE = object()
"""What an indicator's own map means by a tier mapped to null: not that it is uncapped,
and not that it is capped low, but that this access does not support the question."""


def _tier_ceiling(indicator: Indicator, score_card: ScoreCard, access_tier: str) -> object:
    """The best level this indicator may reach at this tier.

    `None` leaves it uncapped, `NOT_ASSESSABLE` means the question cannot be asked here,
    and anything else is a level.
    """
    own = indicator.tier_ceilings
    if own is not None and access_tier in own:
        ceiling = own[access_tier]
        return NOT_ASSESSABLE if ceiling is None else ceiling

    if not score_card.tier_ceilings:
        return None
    if access_tier not in score_card.tier_ceilings:
        known = ", ".join(sorted(score_card.tier_ceilings))
        raise ScoreCardError(
            f"the plan's access tier {access_tier!r} has no ceiling in this score card. "
            f"Tiers with a ceiling: {known}. Add {access_tier!r} to tier_ceilings"
        )
    return score_card.tier_ceilings[access_tier]


def _indicator(
    indicator: Indicator,
    score_card: ScoreCard,
    estimates: Estimates,
    access_tier: str,
    summary_only: frozenset[str],
    audit: AuditResponses | None = None,
    prior: Prior | None = None,
    items: list[ItemRecord] | None = None,
    plan_sha256: str | None = None,
) -> GradedIndicator:
    ceiling = _tier_ceiling(indicator, score_card, access_tier)
    if ceiling is NOT_ASSESSABLE:
        # Before the metric is looked for, not after. A bundle from this tier has no reason
        # to hold it, and reporting that absence as a broken reference would be blaming the
        # score card for a limit the score card is the thing describing.
        return GradedIndicator(
            id=indicator.id,
            name=indicator.name,
            verdict="ungraded",
            reason=(
                f"the score card does not grade this at {access_tier.replace('_', ' ')} access"
            ),
        )

    capped = ceiling if isinstance(ceiling, str) else None
    metric = indicator.metric
    if isinstance(metric, AuditRef):
        return _audited(indicator, score_card, capped, audit)

    if prior is None and any(_needs_prior(ref) for ref in _refs(metric)):
        # Not an error and not a failing grade. A first evaluation of a system has nothing
        # to have moved from, and saying so is the true statement.
        return GradedIndicator(
            id=indicator.id,
            name=indicator.name,
            verdict="ungraded",
            reason="requires a previous test for comparison. Run grade with --prior",
        )

    measured, expression = _measure(
        metric, indicator.id, estimates, summary_only, prior, items, plan_sha256
    )
    value, low, high = _value_of(metric, measured)
    applied = _applied_ceiling(score_card, capped, measured)

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
    return _cap(indicator, decided, score_card, applied, measured, expression, value, access_tier)


def _audited(
    indicator: Indicator,
    score_card: ScoreCard,
    tier_ceiling: str | None,
    audit: AuditResponses | None,
) -> GradedIndicator:
    """Grade an indicator from what a person recorded, capped like any other.

    The engine asserts nothing here beyond the two things it can check: that the level is
    on the ladder the score card declares, and that it does not exceed what this access
    tier may claim. `artefact_provenance` is the reason the second matters. No tier reaches
    the top level for it, because a white box evaluation still cannot show that the model
    it read is the model serving traffic, and the ceiling is where that limit stops being
    a footnote and starts being machine readable.
    """
    if audit is None:
        return GradedIndicator(
            id=indicator.id,
            name=indicator.name,
            verdict="ungraded",
            reason="graded by an assessor. Run grade with --audit and their responses",
        )

    response = audit.responses.get(indicator.id)
    if response is None:
        return GradedIndicator(
            id=indicator.id,
            name=indicator.name,
            verdict="ungraded",
            reason=f"{audit.audit_name} has no response for this indicator",
        )

    if response.level not in score_card.levels:
        raise ScoreCardError(_off_the_ladder(indicator.id, response, score_card))

    built = GradedIndicator(
        id=indicator.id,
        name=indicator.name,
        verdict="graded",
        level=response.level,
        uncapped_level=response.level,
        audit=response,
    )
    if tier_ceiling is None:
        return built

    capped = _worst_of(score_card, response.level, tier_ceiling)
    if capped == response.level:
        return built
    return built.model_copy(
        update={"level": capped, "ceiling": tier_ceiling, "ceiling_reason": "access_tier"}
    )


def _off_the_ladder(indicator_id: str, response: AuditResponse, score_card: ScoreCard) -> str:
    ladder = ", ".join(score_card.levels)
    return (
        f"{indicator_id}: the audit records level {response.level!r}, which is not on the "
        f"score card's ladder ({ladder})"
    )


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
                    f"the likely range crosses the {straddled.level} threshold "
                    f"({straddled.threshold:g}), so the grade is {straddled.level} or {rule.level}"
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
                f"the likely range crosses the {straddled.level} threshold "
                f"({straddled.threshold:g}) and no lower rule applies, so the grade is "
                f"{straddled.level} or none"
            ),
        )
    return _Decision(verdict="ungraded", reason="no rule on the score card applies to this score")


def limit_words(ceiling_reason: str | None, level: str, access_tier: str) -> str:
    """The cap that held a grade down, as a clause."""
    if ceiling_reason == "summary_only":
        return f"summary-only results are capped at {level}"
    return f"{access_tier.replace('_', ' ')} access is capped at {level}"


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
    value: float,
    access_tier: str,
) -> GradedIndicator:
    """Apply the claim ceiling and give the decision its identity.

    A ceiling below the whole indeterminate range settles it: if the grade could not have
    exceeded the ceiling either way, the range collapses and the interval decides nothing.
    A ceiling inside the range lowers its better end, and the reason says so in the same
    words the grade is shown in. A ceiling that changes neither end is not recorded.
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
        value=value,
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
                        f"the likely range allows {' or '.join(decided.between)}, and "
                        f"{limit_words(reason, level, access_tier)}"
                    ),
                }
            )
        if narrowed == list(decided.between):
            return built
        return built.model_copy(
            update={
                "between": narrowed,
                "ceiling": level,
                "ceiling_reason": reason,
                "reason": (
                    f"{decided.reason}; {limit_words(reason, level, access_tier)}, so the "
                    f"grade is {options(narrowed)}"
                ),
            }
        )

    return built


def options(levels: Sequence[str]) -> str:
    """An indeterminate range as words. A single level is open at the bottom."""
    return " or ".join([*levels, "none"] if len(levels) == 1 else levels)


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


def _refs(metric: MetricRef | Expression) -> list[MetricRef]:
    return list(metric.values.values()) if isinstance(metric, Expression) else [metric]


def _needs_prior(ref: MetricRef) -> bool:
    return ref.bundle == "prior" or ref.source == "paired_difference"


def _plain(ref: MetricRef, bundle: Literal["this", "prior"]) -> MetricRef:
    """One of the two figures a paired difference is taken between, as a plain estimate."""
    return ref.model_copy(update={"source": "estimate", "bundle": bundle})


def _measure(
    metric: MetricRef | Expression,
    indicator_id: str,
    estimates: Estimates,
    summary_only: frozenset[str],
    prior: Prior | None = None,
    items: list[ItemRecord] | None = None,
    plan_sha256: str | None = None,
) -> tuple[list[Measured], str | None]:
    measured = [
        _difference(ref, estimates, summary_only, prior, items, plan_sha256, indicator_id)
        if ref.source == "paired_difference" and prior is not None
        else _resolve(ref, *_where(ref, estimates, summary_only, prior), indicator_id)
        for ref in _refs(metric)
    ]
    return measured, metric.expression if isinstance(metric, Expression) else None


def _where(
    ref: MetricRef, estimates: Estimates, summary_only: frozenset[str], prior: Prior | None
) -> tuple[Estimates, frozenset[str]]:
    """Which bundle this reference reads, and which packs emitted no items in it.

    The summary-only set travels with the bundle rather than with the run. A pack that was
    summary only last time and emits items now would otherwise cap a grade on evidence
    that no longer applies, or fail to cap one on evidence that does.
    """
    if ref.bundle == "prior" and prior is not None:
        return prior.estimates, prior.summary_only
    return estimates, summary_only


def _difference(
    ref: MetricRef,
    estimates: Estimates,
    summary_only: frozenset[str],
    prior: Prior,
    items: list[ItemRecord] | None,
    plan_sha256: str | None,
    indicator_id: str,
) -> Measured:
    """This bundle's figure minus the prior one's, with an interval over the change itself.

    Paired where both bundles ran the same frozen plan and hold the same items, so that a
    system finding the same items hard both times has that agreement taken out of the
    interval rather than counted twice. Anywhere else the two stored intervals are combined
    as though independent. Pairing is checked against the plan hash and the item ids, never
    assumed, and `difference` records which comparison ran and why.
    """
    now = _resolve(_plain(ref, "this"), estimates, summary_only, indicator_id)
    before = _resolve(_plain(ref, "prior"), prior.estimates, prior.summary_only, indicator_id)
    measured = Measured(
        ref=ref,
        n=min(now.n, before.n),
        stratum=dict(ref.stratum),
        summary_only=now.summary_only or before.summary_only,
    )
    if (
        now.value is None
        or now.low is None
        or now.high is None
        or before.value is None
        or before.low is None
        or before.high is None
    ):
        return measured

    rate = any(
        entry.k is not None
        for entry in estimates.estimates
        if entry.metric == ref.name
        and entry.pack_id == ref.pack_id
        and entry.stratum == ref.stratum
    )
    joined, reason = _pairs(ref, rate, items, prior, plan_sha256)
    figures: dict[str, float | int | str] = {"now": now.value, "before": before.value}

    if joined is None:
        value, low, high = paired.unpaired_difference(
            (now.value, now.low, now.high), (before.value, before.low, before.high)
        )
        difference = Difference(
            comparison="unpaired",
            reason=reason,
            estimator="wilson_difference" if rate else "limits_difference",
            parameters=figures,
            reference=(
                paired.WILSON_DIFFERENCE_REFERENCE if rate else paired.LIMITS_DIFFERENCE_REFERENCE
            ),
        )
    else:
        computed = paired.paired_difference(joined, bounded=rate)
        value, low, high = computed.point, computed.low, computed.high
        difference = Difference(
            comparison="paired",
            reason=reason,
            estimator="paired_clt",
            parameters={
                **figures,
                "items": computed.items,
                "standard_error": computed.standard_error,
                "z": Z_95,
                "confidence": 0.95,
            },
            reference=paired.PAIRED_REFERENCE,
        )
    return measured.model_copy(
        update={"value": value, "low": low, "high": high, "difference": difference}
    )


def _pairs(
    ref: MetricRef,
    rate: bool,
    items: list[ItemRecord] | None,
    prior: Prior,
    plan_sha256: str | None,
) -> tuple[list[tuple[float, float]] | None, str]:
    """Both bundles' per-item scores joined on `item_id`, or None and why they cannot be.

    The same plan hash is the precondition and the same item ids are the check on it. A
    unit that failed in one run leaves the plans identical and the items not, and pairing
    whatever survived in both would decide which items count after seeing the results.
    """
    if plan_sha256 is None or prior.plan_sha256 is None:
        return None, "one of the tests does not record its plan"
    if plan_sha256 != prior.plan_sha256:
        return None, (
            f"the tests used different plans ({plan_sha256[:8]} and {prior.plan_sha256[:8]})"
        )
    if items is None or prior.items is None:
        which = "this test" if items is None else "the previous test"
        return None, f"{which} has no item-level results ({ITEMS_NAME})"

    now, before = _per_item(ref, rate, items), _per_item(ref, rate, prior.items)
    if now.keys() != before.keys():
        return None, f"{len(now.keys() ^ before.keys())} item(s) appear in only one test"
    if len(now) < 2:
        return None, f"only {len(now)} item(s) to compare; at least 2 are needed"
    joined = [(now[item_id], before[item_id]) for item_id in sorted(now)]
    return joined, f"compared item by item: {len(joined)} items, plan {plan_sha256[:8]}"


def _per_item(ref: MetricRef, rate: bool, items: list[ItemRecord]) -> dict[str, float]:
    """Each item's score on one metric in one cell, averaged over its replicates."""
    observed: dict[str, list[float]] = {}
    for item in items:
        if ref.pack_id is not None and item.pack_id != ref.pack_id:
            continue
        if any(item.stratum.get(key, "(unset)") != value for key, value in ref.stratum.items()):
            continue
        reported = item.outcome if rate else item.score
        if ref.name in reported:
            observed.setdefault(item.item_id, []).append(float(reported[ref.name]))
    return {item_id: fmean(scores) for item_id, scores in observed.items()}


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
        return "no score could be computed"
    where = ", ".join(sorted({one.ref.name for one in empty}))
    if all(one.n == 0 for one in empty):
        return f"no results for {where}"
    return f"{where} has results but no score"


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
            f"{indicator_id}: {ref.name!r} has no pack_id and {len(estimates.packs)} packs "
            f"contributed ({', '.join(estimates.packs)}). Set pack_id to one of them"
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


def _keyed(shape: frozenset[str]) -> str:
    """One cell shape, named the way a score card would write it."""
    return ", ".join(sorted(shape))


def _worst(ref: MetricRef, estimates: Estimates, contaminated: bool, indicator_id: str) -> Measured:
    """The weakest cell of the rollup, through the same function `estimate` uses."""
    wanted = frozenset(ref.keys)
    cells = [
        entry
        for entry in estimates.estimates
        if entry.metric == ref.name and entry.pack_id == ref.pack_id and entry.stratum
    ]
    shapes = {frozenset(entry.stratum) for entry in cells}
    held = "; ".join(sorted(_keyed(shape) for shape in shapes)) or "none"

    if not cells:
        raise ScoreCardError(
            f"{indicator_id}: no cell of {ref.name!r} has a stratum in this bundle. "
            "Run `estimate` with --by"
        )
    if wanted and wanted not in shapes:
        raise ScoreCardError(
            f"{indicator_id}: no cell of {ref.name!r} is keyed by {_keyed(wanted)}. "
            f"This bundle has cells keyed: {held}. Run `estimate` with that key"
        )
    nested = sorted(
        (_keyed(coarse), _keyed(fine)) for coarse in shapes for fine in shapes if coarse < fine
    )
    if not wanted and nested:
        coarse, fine = nested[0]
        raise ScoreCardError(
            f"{indicator_id}: {ref.name!r} has cells keyed ({coarse}) and cells keyed "
            f"({fine}) inside them. Set `keys` to the dimension to rank. This bundle has: "
            f"{held}"
        )

    subset = estimates.model_copy(
        update={
            "estimates": [
                entry
                for entry in estimates.estimates
                if entry.pack_id == ref.pack_id
                and (not wanted or frozenset(entry.stratum) == wanted)
            ]
        }
    )
    found = estimate_items.worst_stratum(
        subset, ref.name, min_n=ref.min_n, higher_is_better=ref.higher_is_better
    )
    if found.worst is None:
        thin = len(found.excluded)
        over = f" keyed by {_keyed(wanted)}" if wanted else ""
        raise ScoreCardError(
            f"{indicator_id}: no stratum of {ref.name!r}{over} reaches n={ref.min_n}. "
            f"{thin} cell(s) are below it"
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
    which = "the prior bundle" if ref.bundle == "prior" else "this bundle"
    return f"{indicator_id}: no {kind} named {ref.name!r}{pack}{where} in {which}"


def indicator_at(
    score_card: ScoreCard, source: str | None, indicator_id: str, *rest: Sequence[positions.Step]
) -> tuple[int, int] | None:
    """Where an indicator was written in the score card, or None.

    `rest` are finer targets tried in order before falling back to the indicator's own
    `id` and then to the whole block, so a problem about one rule points at that rule and
    a problem about the indicator still lands somewhere useful when the card is shaped
    differently from what the caller guessed.
    """
    index = next(
        (at for at, indicator in enumerate(score_card.indicators) if indicator.id == indicator_id),
        None,
    )
    if index is None:
        return None
    candidates: list[Sequence[positions.Step]] = [("indicators", index, *step) for step in rest]
    candidates.append(("indicators", index, "id"))
    candidates.append(("indicators", index))
    return positions.first(source, *candidates)


def check(
    score_card: ScoreCard,
    estimates: Estimates,
    access_tier: str = "",
    audit: AuditResponses | None = None,
    prior: Prior | None = None,
    score_card_path: Path | None = None,
) -> list[Problem]:
    """Cross-check a score card against a bundle. Returns every problem, not the first.

    Run before anything is graded, so a score card with four broken references reports
    four rather than one per attempt.

    An indicator the score card marks unassessable at `access_tier` is skipped, because the
    metric it names is one this tier had no way to produce and its absence is the score
    card being right rather than wrong.

    `score_card_path` is what lets a problem name the line the indicator was written on.
    Without it the problems are the same problems, carrying no position.
    """
    source = positions.load_source(score_card_path) if score_card_path is not None else None
    where = str(score_card_path) if score_card_path is not None else None
    problems: list[Problem] = []

    def report(code: str, subject: str, message: str, *rest: Sequence[positions.Step]) -> None:
        found = indicator_at(score_card, source, subject, *rest)
        problems.append(
            Problem(
                code=code,
                message=message,
                path=where,
                line=found[0] if found else None,
                column=found[1] if found else None,
                subject=subject,
            )
        )

    if audit is not None:
        declared = {indicator.id for indicator in score_card.indicators}
        audited = {
            indicator.id
            for indicator in score_card.indicators
            if isinstance(indicator.metric, AuditRef)
        }
        for answered in sorted(audit.responses):
            if answered not in declared:
                report(
                    "audit_indicator_undeclared",
                    answered,
                    f"{audit.audit_name} answers {answered!r}, which this score card does "
                    "not declare",
                )
            elif answered not in audited:
                report(
                    "audit_indicator_computed",
                    answered,
                    f"{audit.audit_name} answers {answered!r}, which this score card "
                    "computes from the bundle. Remove it from the audit responses",
                )

    for indicator in score_card.indicators:
        if access_tier and _tier_ceiling(indicator, score_card, access_tier) is NOT_ASSESSABLE:
            continue
        metric = indicator.metric
        if isinstance(metric, AuditRef):
            continue
        has_interval = isinstance(metric, MetricRef) and metric.source in INTERVAL_SOURCES

        for position, rule in enumerate(indicator.assessment):
            if rule.condition in INTERVAL_CONDITIONS and not has_interval:
                carries = (
                    "an expression, which has no interval"
                    if isinstance(metric, Expression)
                    else f"source {metric.source!r}, which carries no interval"
                )
                report(
                    "interval_condition_without_interval",
                    indicator.id,
                    f"{indicator.id}: rule {rule.level} uses {rule.condition} against {carries}",
                    ("assessment", position, "condition"),
                    ("assessment", position),
                )

        if isinstance(metric, Expression):
            used = expressions.names(metric.expression)
            declared = set(metric.values)
            for name in sorted(used - declared):
                report(
                    "expression_name_undeclared",
                    indicator.id,
                    f"{indicator.id}: {name!r} is in the expression and not in values",
                    ("metric", "expression"),
                )
            for name in sorted(declared - used):
                report(
                    "expression_value_unused",
                    indicator.id,
                    f"{indicator.id}: {name!r} is in values and not in the expression",
                    ("metric", "values", name),
                    ("metric", "values"),
                )

        for ref in _refs(metric):
            if _needs_prior(ref) and prior is None:
                # Nothing to check against, and nothing wrong with the card. The indicator
                # comes back ungraded rather than broken.
                continue
            try:
                if ref.source == "paired_difference" and prior is not None:
                    _resolve(_plain(ref, "this"), estimates, frozenset(), indicator.id)
                    _resolve(_plain(ref, "prior"), prior.estimates, frozenset(), indicator.id)
                else:
                    _resolve(
                        ref,
                        _where(ref, estimates, frozenset(), prior)[0],
                        frozenset(),
                        indicator.id,
                    )
            except ScoreCardError as exc:
                report("metric_not_found", indicator.id, str(exc), ("metric",))
    return problems


def summary_only_packs(run_dir: Path) -> frozenset[str]:
    """Packs the frozen plan records as emitting no items. Empty where there is no lock."""
    path = run_dir / LOCK_NAME
    if not path.exists():
        return frozenset()
    return frozenset(pack.id for pack in load_lock(path).packs if not pack.emits_items)


def load_prior(run_dir: Path) -> Prior:
    """The earlier evaluation, read the same way this one is. Offline, like everything here."""
    return Prior(
        estimates=load_estimates(run_dir),
        summary_only=summary_only_packs(run_dir),
        plan_sha256=plan_hash(run_dir),
        items=run_items(run_dir),
    )


def run_items(run_dir: Path) -> list[ItemRecord] | None:
    """The records a run directory holds, or None where it holds no items.jsonl.

    Absent is a legitimate bundle, one that was hand-assembled from estimates, and it
    grades everything except a paired difference, which falls back and says so."""
    path = run_dir / ITEMS_NAME
    return estimate_items.load_items(path) if path.is_file() else None


def access_tier(run_dir: Path) -> str:
    """The tier the plan was frozen with. Not a flag: a grade names the tier it was capped by."""
    path = run_dir / LOCK_NAME
    if not path.exists():
        raise ScoreCardError(
            f"{run_dir} has no {LOCK_NAME}, so its access tier is unknown. Grade the "
            "directory `touchstone run` wrote"
        )
    return load_lock(path).access_tier


def load_audit(path: Path) -> AuditResponses:
    """Read a file of audit responses and check it against itself."""
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ScoreCardError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScoreCardError(f"{path} is not a set of audit responses")
    try:
        return AuditResponses.model_validate(raw)
    except ValidationError as exc:
        raise ScoreCardError(f"{path}: {exc}") from exc


def copy_audit(path: Path, run_dir: Path) -> tuple[Path, str]:
    """Put the responses in the bundle and hash them. Returns where they landed.

    A grade read out of a file that lives on the assessor's laptop cannot be recomputed
    from the bundle, which is what every other input to this command already avoids. The
    same-file case is the one the run directory hits when the responses are already there,
    and copying a file onto itself raises.
    """
    destination = run_dir / AUDIT_NAME
    run_dir.mkdir(parents=True, exist_ok=True)
    if path.resolve() != destination.resolve():
        shutil.copyfile(path, destination)
    return destination, sha256_file(destination)


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
    """The score card as a person reads it: each grade, the score behind it, and why."""
    rendered: list[str] = []
    for indicator in scorecard.indicators:
        if rendered:
            rendered.append("")
        rendered.append(f"{indicator.name} ({indicator.id})" if indicator.name else indicator.id)
        rendered.append(f"  Grade: {_grade_words(indicator)}")
        score = _score_words(indicator)
        if score:
            rendered.append(f"  Score: {score}")
        why = reason_words(indicator, scorecard.access_tier)
        if why:
            rendered.append(f"  Reason: {why}")
        for one in indicator.measured:
            if one.difference is not None and one.difference.comparison == "unpaired":
                rendered.append(f"  Compared by totals: {one.difference.reason}")
    return rendered


def _grade_words(indicator: GradedIndicator) -> str:
    if indicator.verdict == "graded" and indicator.level is not None:
        return indicator.level
    if indicator.verdict == "indeterminate":
        return f"{options(indicator.between)}, inconclusive"
    return "not graded"


def reason_words(indicator: GradedIndicator, access_tier: str) -> str | None:
    """The reason for the grade as a sentence, including a cap that held it down. The
    printed score card and the PDF both show this, so the two cannot disagree."""
    text = indicator.reason
    if indicator.ceiling is None:
        return text[:1].upper() + text[1:] if text else None
    limit = limit_words(indicator.ceiling_reason, indicator.ceiling, access_tier)
    if text is None:
        given = "assessed as" if indicator.audit is not None else "scored"
        text = f"{given} {indicator.uncapped_level}; {limit}"
    elif indicator.verdict == "indeterminate":
        shown = options(indicator.between)
        if not text.endswith(f"so the grade is {shown}"):
            # A bundle graded before the reason carried the ceiling holds the range before
            # the cap in `reason` and the range after it in `between`.
            text = f"{text}; {limit}, so the grade is {shown}"
    return text[:1].upper() + text[1:]


def _score_words(indicator: GradedIndicator) -> str | None:
    """The number the grade was decided on, with its likely range and how many results.

    An expression shows its own value and the formula that produced it, and no range and
    no count: it has neither. Its inputs are in `scorecard.json`, each with its own count,
    and putting them on one line would suggest a shared one.
    """
    if indicator.value is None:
        return None
    if indicator.expression is not None:
        return f"{indicator.value:.4g} ({indicator.expression})"

    shown = indicator.measured[0] if indicator.measured else None
    if shown is None:
        return f"{indicator.value:.4g}"

    text = f"{indicator.value:.4g}"
    if shown.difference is not None:
        text = f"change of {indicator.value:+.4g} since the previous test"
    if shown.low is not None and shown.high is not None:
        text += f", likely range {shown.low:.4g} to {shown.high:.4g}"
    text += f", {shown.n} results"
    if shown.stratum:
        text += ", " + ", ".join(f"{key} {value}" for key, value in sorted(shown.stratum.items()))
    if shown.difference is not None and shown.difference.comparison == "paired":
        text += ", compared item by item"
    return text
