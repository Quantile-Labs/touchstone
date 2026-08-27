"""What the harness computes from the observations, and how it computed it.

02-DESIGN.md section 6 rule 3: the bundle is self-describing. An estimate that does not
name its estimator is a number a reviewer has to take on trust, so every record here
carries the method, its parameters and a citation, and the arithmetic can be redone in R,
in a spreadsheet, or by hand without this code.
"""

from pydantic import BaseModel, Field


class Estimate(BaseModel):
    metric: str = Field(min_length=1)
    """The outcome or score key this estimates."""

    stratum: dict[str, str] = Field(default_factory=dict)
    """Which cell of the rollup. Empty is the whole sample."""

    pack_id: str | None = None
    """Which pack this was computed over. None means it pools every pack that ran, which
    is only meaningful where they measure the same thing. Kept off `stratum` so that
    field stays what the pack declared and cannot collide with a key of the same name."""

    n: int = Field(ge=0)
    """The denominator. Printed beside the point estimate, always."""

    point: float | None = None
    """None where n is 0. A cell with no items has no estimate, and says so."""

    low: float
    high: float

    k: int | None = None
    """Successes, for a proportion. None for a continuous score."""

    estimator: str = Field(min_length=1)
    """`wilson`, `bootstrap_bca`. Named so the arithmetic can be redone elsewhere."""

    parameters: dict[str, float | int | str] = Field(default_factory=dict)
    """Everything the estimator needed beyond the data. z, resamples, confidence."""

    reference: str = Field(min_length=1)
    """The published source of the estimator. The citation is what makes it reviewable."""

    model_config = {"extra": "forbid"}


class WorstStratum(BaseModel):
    """The weakest cell of a rollup, and the cells the minimum size rule kept out of it."""

    metric: str = Field(min_length=1)
    min_n: int = Field(ge=1)
    higher_is_better: bool = True

    worst: Estimate | None = None
    """None when no cell reaches `min_n`. That is a finding, not a missing value."""

    excluded: list[Estimate] = Field(default_factory=list)
    """Cells below `min_n`. Reported rather than dropped: a rollup that quietly discards
    its thin cells reads as coverage it does not have."""

    selected_from: int = Field(default=0, ge=0)
    """How many eligible cells the winner was ranked against. The interval on `worst` is
    widened to hold over all of them, so this is the number that makes it readable, and a
    reader who sees it rise knows the point estimate is being selected harder."""

    model_config = {"extra": "forbid"}


class CalibrationBin(BaseModel):
    """One rung of a reliability curve."""

    low: float = Field(ge=0.0, le=1.0)
    high: float = Field(ge=0.0, le=1.0)
    n: int = Field(ge=1)
    mean_confidence: float
    accuracy: float

    @property
    def gap(self) -> float:
        """Signed. Positive is overconfidence, which is the direction that does harm."""
        return self.mean_confidence - self.accuracy

    model_config = {"extra": "forbid"}


class Calibration(BaseModel):
    """Whether a stated confidence means what it says."""

    metric: str = Field(min_length=1)
    pack_id: str | None = None
    """Which pack declared this outcome as the one its confidence is a claim about."""

    n: int = Field(ge=0)
    ece: float | None = None
    """None when nothing was scored. Expected calibration error, sample weighted."""

    bins: list[CalibrationBin] = Field(default_factory=list)

    unscored: int = Field(default=0, ge=0)
    """Items carrying the outcome but no confidence. They cannot be binned, and are
    counted here rather than dropped without trace."""

    estimator: str = "ece_equal_width"
    parameters: dict[str, float | int | str] = Field(default_factory=dict)
    reference: str = Field(min_length=1)

    model_config = {"extra": "forbid"}


class ReplicateVariance(BaseModel):
    """How much of a result is the system and how much is the run."""

    metric: str = Field(min_length=1)
    pack_id: str | None = None

    rates: dict[int, tuple[int, int]] = Field(default_factory=dict)
    """replicate -> (successes, observations). Each carries its own denominator."""

    mean: float | None = None
    sd: float | None = None
    """Sample standard deviation across replicate rates. None below two replicates:
    one run cannot report its own stability."""

    spread: float | None = None
    """Highest replicate rate minus lowest. What a grade boundary has to clear."""

    unstable_items: int = Field(default=0, ge=0)
    """Items seen in more than one replicate that did not answer the same way each time."""

    repeated_items: int = Field(default=0, ge=0)
    """Items seen in more than one replicate. The denominator for the line above."""

    model_config = {"extra": "forbid"}


class Estimates(BaseModel):
    """The `estimates.json` of an evidence bundle."""

    touchstone_version: str
    items: int = Field(ge=0)
    """How many item records were read. The rollup's grand total."""

    grouped_by: list[str] = Field(default_factory=list)
    """The stratum keys the rollup used, in the order they were requested.

    Several keys are rolled up one at a time and then crossed, so the cells below carry
    one key or all of them. Which shape an estimate is keyed by is on the estimate."""

    packs: list[str] = Field(default_factory=list)
    """Which packs contributed records. More than one and every estimate carrying a null
    `pack_id` pools them, which a reader has to be told rather than left to notice."""

    pooled: bool = False
    """True when more than one pack contributed. Set so the flag survives into the bundle
    rather than living only in what the command printed."""

    estimates: list[Estimate] = Field(default_factory=list)

    calibration: list[Calibration] = Field(default_factory=list)
    """One per boolean outcome, where any item reported a confidence."""

    replicate_variance: list[ReplicateVariance] = Field(default_factory=list)
    """One per boolean outcome, where the plan asked for more than one replicate."""

    model_config = {"extra": "forbid"}
