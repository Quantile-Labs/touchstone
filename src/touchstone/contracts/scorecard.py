"""What an analyst asserts a grade means, and what the harness decided.

The rubric is data. `levels` is an ordered list the score card declares, best first, and
nothing here or in `grade.py` knows how many there are or what they are called. DQI uses
eight; ASQI uses five; a score card written for one client may use three. An engine that
hardcodes A to E cannot carry a standard that has not been finished yet, and this one is
not finished yet.

The conditions ending `_ci_lower`, `_ci_upper` and `_by_interval` are the ones ASQI cannot
express. See `grade.py` for what they do to a verdict.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Condition = Literal[
    "greater_equal",
    "greater_than",
    "less_equal",
    "less_than",
    "equal_to",
    "greater_equal_ci_lower",
    "less_equal_ci_upper",
    "threshold_crossed_by_interval",
]

INTERVAL_CONDITIONS = frozenset(
    {"greater_equal_ci_lower", "less_equal_ci_upper", "threshold_crossed_by_interval"}
)
"""Conditions that read `low` or `high`. A source that carries no interval cannot satisfy
one, and asking is a plan error rather than a false answer."""

Source = Literal["estimate", "worst_stratum", "calibration", "replicate_variance"]

INTERVAL_SOURCES = frozenset({"estimate", "worst_stratum"})
"""The two that carry a Wilson or BCa interval. An ECE and a replicate spread are single
numbers: neither has a sampling distribution this codebase is willing to assert."""


class MetricRef(BaseModel):
    """Which number in `estimates.json` an indicator is about."""

    source: Source = "estimate"
    name: str = Field(min_length=1)
    """The metric key, as the pack reported it."""

    pack_id: str | None = None
    """None selects the pooled figure. On a multi-pack run that is rarely what is meant,
    and `grade` says so rather than grading two packs as though they measured one thing."""

    stratum: dict[str, str] = Field(default_factory=dict)
    """Empty is the whole sample. Ignored by `worst_stratum`, which searches cells."""

    keys: list[str] = Field(default_factory=list)
    """`worst_stratum` only: search cells keyed by exactly these stratum keys.

    Without it every cell carrying any stratum is a candidate, so two indicators that mean
    to ask about different dimensions ask the same question and return the same cell. An
    index with a geographic indicator and a language indicator needs them to differ."""

    min_n: int = Field(default=30, ge=1)
    """`worst_stratum` only: the smallest cell allowed to be the worst one."""

    higher_is_better: bool = True
    """`worst_stratum` only: which end of the ranking the weakest cell is at."""

    model_config = {"extra": "forbid"}


class Expression(BaseModel):
    """An arithmetic combination of several metrics, evaluated without `eval`."""

    expression: str = Field(min_length=1)
    values: dict[str, MetricRef] = Field(min_length=1)
    """Variable name in the expression to the metric it stands for."""

    model_config = {"extra": "forbid"}


class Rule(BaseModel):
    """One rung of the ladder: the level this awards, and what has to hold to award it."""

    level: str = Field(min_length=1)
    condition: Condition
    threshold: float
    """Every condition here compares against a number, so this is required. A rule with no
    threshold would be a rule that always holds, which is a typo, not a rubric."""

    description: str | None = None

    model_config = {"extra": "forbid"}


class Indicator(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    name: str | None = None
    metric: MetricRef | Expression
    assessment: list[Rule] = Field(min_length=1)
    """Ordered, best level first. The first rule that holds decides the grade."""

    tier_ceilings: dict[str, str | None] | None = None
    """Overrides the score card's map for this indicator alone.

    A tier mapped to `null` is one where this indicator is **not assessable**: it returns
    `ungraded` naming the tier, and the metric it would have read is never looked for, so
    a bundle that legitimately does not hold it is not an error.

    Required because the ceiling is a property of the pair. A black box evaluation can
    measure headline accuracy completely and cannot measure calibration at all, and one
    ceiling for a whole card either caps the first for no reason or lets the second be
    claimed on evidence that does not exist."""

    model_config = {"extra": "forbid"}


class ScoreCard(BaseModel):
    """The rubric, its ladder, and the ceilings that stop a claim exceeding its evidence."""

    score_card_name: str = Field(min_length=1)

    levels: list[str] = Field(min_length=2)
    """Ordered best first. Every level named by a rule or a ceiling has to appear here."""

    tier_ceilings: dict[str, str] = Field(default_factory=dict)
    """Access tier to the best level it may reach. The tier vocabulary is the score card's,
    not this engine's, so a new tier is a YAML change. A tier absent from this map is
    uncapped, which has to be written down rather than assumed: an unrecognised tier is a
    hard error in `grade.py`."""

    summary_only_ceiling: str | None = None
    """The best level a metric from a pack that emitted no items may reach. None leaves it
    uncapped, which 02-DESIGN.md section 3.4 advises against."""

    indicators: list[Indicator] = Field(min_length=1)

    @model_validator(mode="after")
    def _levels_are_declared(self) -> "ScoreCard":
        known = set(self.levels)
        if len(known) != len(self.levels):
            raise ValueError("levels has a duplicate")

        named = {ceiling for ceiling in self.tier_ceilings.values()}
        if self.summary_only_ceiling is not None:
            named.add(self.summary_only_ceiling)
        for indicator in self.indicators:
            named.update(rule.level for rule in indicator.assessment)
            for ceiling in (indicator.tier_ceilings or {}).values():
                if ceiling is not None:
                    named.add(ceiling)

        unknown = sorted(named - known)
        if unknown:
            raise ValueError(f"level(s) not in `levels`: {', '.join(unknown)}")

        ids = [indicator.id for indicator in self.indicators]
        if len(set(ids)) != len(ids):
            raise ValueError("indicator ids are not unique")
        return self

    def rank(self, level: str) -> int:
        """Position in the ladder. Lower is better, because `levels` is best first."""
        return self.levels.index(level)

    model_config = {"extra": "forbid"}


Verdict = Literal["graded", "indeterminate", "ungraded"]
"""`graded` awarded a level. `indeterminate` is the interval straddling a boundary, which
is a finding. `ungraded` is no rule holding at all, or nothing to grade, which is a
different finding and is not the same as the worst level."""


class Measured(BaseModel):
    """The number an indicator was decided on, and where in the bundle it came from."""

    ref: MetricRef
    value: float | None = None
    low: float | None = None
    high: float | None = None
    """None where the source carries no interval, or where nothing was measured."""

    n: int = Field(default=0, ge=0)

    stratum: dict[str, str] = Field(default_factory=dict)
    """The cell this number came from. Copied from the estimate rather than from the
    reference, because `worst_stratum` chooses the cell and a report that says a system
    was weakest somewhere without saying where is not a finding."""

    summary_only: bool = False
    """True when the pack behind this number emitted no items. Its ceiling applies."""

    model_config = {"extra": "forbid"}


class GradedIndicator(BaseModel):
    """One indicator's outcome, and enough of the working to argue with it."""

    id: str
    name: str | None = None
    verdict: Verdict
    level: str | None = None
    """The level awarded, after any ceiling. None unless the verdict is `graded`."""

    rule: Rule | None = None
    """The rule that decided it. None for `ungraded`, and for `indeterminate` this is the
    rule whose boundary the interval straddles."""

    between: list[str] = Field(default_factory=list)
    """For `indeterminate`, the level refused and the next one down, in that order. The
    honest statement is that the grade is one of these and the evidence does not say
    which."""

    reason: str | None = None
    """Why, in one line, for `indeterminate` and `ungraded`. Printed in the report."""

    uncapped_level: str | None = None
    """What the ladder awarded before a ceiling applied. Equal to `level` when nothing
    capped it, and kept so a reader can see the claim the evidence supported and the
    reason it was not made."""

    ceiling: str | None = None
    ceiling_reason: str | None = None
    """`access_tier` or `summary_only`. Set only where a ceiling actually bit."""

    measured: list[Measured] = Field(default_factory=list)
    """Every number read. More than one where the metric was an expression."""

    value: float | None = None
    """The number the ladder was actually walked against.

    Equal to the single measured value for a plain reference, and the computed result for
    an expression, where it is the only place that number appears. A report that grades a
    difference between two rates and prints one of the rates beside the grade is showing a
    number that did not decide anything."""

    expression: str | None = None
    """The formula, where one was used. It carries no interval, by design: combining two
    intervals needs their correlation, and a bundle does not record it."""

    model_config = {"extra": "forbid"}


class Scorecard(BaseModel):
    """The `scorecard.json` of an evidence bundle."""

    touchstone_version: str
    score_card_name: str
    access_tier: str
    """Copied from the frozen plan, not from a flag, so the ceiling that applied is part
    of the evidence."""

    levels: list[str]
    """The ladder this was graded on, carried so the bundle is readable without the score
    card that produced it."""

    plan_sha256: str | None = None
    """The frozen plan these grades were asserted against. A grade is only meaningful
    beside the thresholds that were fixed before the run."""

    indicators: list[GradedIndicator] = Field(default_factory=list)

    model_config = {"extra": "forbid"}
