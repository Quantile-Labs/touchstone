"""The observation a pack emits, one per evaluated item.

This is the load-bearing contract. Packs report what happened; Touchstone computes
every statistic from these records, so rates, intervals and stratified breakdowns are
derivable by anyone holding the bundle.
"""

from pydantic import BaseModel, Field


class ItemRecord(BaseModel):
    item_id: str = Field(min_length=1)
    """Stable across runs. The join key for re-analysis."""

    stratum: dict[str, str] = Field(default_factory=dict)
    """Open dimensions to group by. Never an enum: locale belongs in packs, not here."""

    outcome: dict[str, bool] = Field(default_factory=dict)
    """Booleans become rates with a denominator."""

    score: dict[str, float] = Field(default_factory=dict)
    """Continuous measures become means with intervals."""

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    """Enables calibration and the confident-and-wrong rate."""

    cost: dict[str, float] = Field(default_factory=dict)

    trace_ref: str | None = None
    """Path inside the bundle to the full prompt and response."""

    replicate: int = Field(default=0, ge=0)
    """Which repeat this is. Between-replicate variance needs it."""

    model_config = {"extra": "forbid"}
