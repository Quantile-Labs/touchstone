# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""What an interval covers, what it leaves out, and what it assumes.

The interval on a figure accounts for sampling alone. The budget lists that alongside every
other source this tool knows of, sized where the rows allow and `unquantified` where they do
not, so what a figure leaves out is stated in the bundle rather than in prose a reader has
to go looking for. The assumptions are the premises the estimators rest on, each with what
checking it found, or that it was not checked.
"""

from math import sqrt

from touchstone.contracts.estimates import (
    Assumption,
    Estimate,
    ReplicateVariance,
    UncertaintyBudget,
    UncertaintyComponent,
)
from touchstone.stats.proportion import Z_95
from touchstone.stats.replicates import HOMOGENEITY_REFERENCE, homogeneity

ALPHA = 0.05
"""Below this p-value, replicate rates are taken to differ by more than chance."""

UNQUANTIFIED = (
    ("marking", "no agreement study between how outcomes were marked and a reference marking"),
    ("item_selection", "no measure of how well the items represent the use a claim is about"),
    ("item_leakage", "no test of whether the system saw the items before it was evaluated"),
    ("endpoint_identity", "no check that the endpoint that answered is the system named"),
)
"""Sources no row can size. Each stays `unquantified` until something measures it."""


def _sampling(entry: Estimate, spread: ReplicateVariance | None) -> list[UncertaintyComponent]:
    """The sampling part of a figure's uncertainty, split in two where replicates allow.

    Without the split it is read off the stored interval, half its width over the `z` it
    was built with, so the budget and the interval cannot disagree. The normal standard
    error off the point would read zero at a rate of 0 or 1, where the interval does not.
    """
    parts = spread.components if spread is not None else None
    if parts is not None:
        return [
            UncertaintyComponent(
                source=source,
                magnitude=sqrt(term / parts.items),
                method=f"{parts.estimator}, the {name} term over {parts.items} items",
                reference=parts.reference,
            )
            for source, name, term in (
                ("completion_sampling", "completion", parts.completion),
                ("item_sampling", "item", parts.item),
            )
        ]
    z = float(entry.parameters.get("z", Z_95))
    return [
        UncertaintyComponent(
            source="sampling",
            magnitude=(entry.high - entry.low) / (2 * z),
            method=f"half the width of the {entry.estimator} interval over z = {z:.4f}",
            reference=entry.reference,
        )
    ]


def budget(entry: Estimate, spread: ReplicateVariance | None) -> UncertaintyBudget | None:
    """The budget for one whole-sample figure. None for a figure with no point estimate.

    `spread` is the replicate variance for the same outcome and pack, where there is one.
    """
    if entry.point is None:
        return None
    return UncertaintyBudget(
        metric=entry.metric,
        pack_id=entry.pack_id,
        point=entry.point,
        components=_sampling(entry, spread)
        + [
            UncertaintyComponent(source=source, magnitude="unquantified", method=method)
            for source, method in UNQUANTIFIED
        ],
    )


FUNCTIONAL_FORM = (
    "Each item has one probability of success, and every trial of it is a draw at that probability"
)


def _functional_form(spread: ReplicateVariance) -> Assumption | None:
    tested = homogeneity(spread.rates)
    if tested is None:
        return None
    statistic, df, p_value = tested
    rates = ", ".join(f"{k / n:.3f}" for k, n in spread.rates.values() if n)
    test = f"chi-square {statistic:.2f} on {df} df, p = {p_value:.3g}"
    violated = p_value < ALPHA
    finding = (
        f"replicate rates {rates} differ by more than chance allows ({test}). The system "
        "changed between replicates, and the interval treats every trial as one population"
        if violated
        else f"replicate rates {rates} are within chance ({test})"
    )
    return Assumption(
        name="functional_form",
        statement=FUNCTIONAL_FORM,
        metric=spread.metric,
        pack_id=spread.pack_id,
        result="violated" if violated else "consistent",
        finding=finding,
        method="pearson_chi_square_homogeneity",
        parameters={"statistic": statistic, "df": df, "p_value": p_value, "alpha": ALPHA},
        reference=HOMOGENEITY_REFERENCE,
    )


def assumptions(packs: list[str], spreads: list[ReplicateVariance]) -> list[Assumption]:
    """The three premises NIST AI 800-3 section 6.2 names, each checked where the rows allow."""
    pooled = (
        f" The figures carrying no pack pool {len(packs)} packs, where it is least likely to hold"
        if len(packs) > 1
        else ""
    )
    checked = [found for spread in spreads if (found := _functional_form(spread)) is not None]
    return [
        Assumption(
            name="unidimensional",
            statement="The items of a figure measure one construct",
            result="not checked",
            finding="checking it needs a latent variable model over the rows, and the "
            f"estimators here fit none.{pooled}",
        ),
        *(
            checked
            or [
                Assumption(
                    name="functional_form",
                    statement=FUNCTIONAL_FORM,
                    result="not checked",
                    finding="the plan ran one replicate, so no item was tried twice",
                )
            ]
        ),
        Assumption(
            name="independent_items",
            statement="Items are independent of one another once each is scored",
            result="not checked",
            finding="checking it needs item groups, such as items sharing a source document, "
            "and the rows do not carry them",
        ),
    ]
