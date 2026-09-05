# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""A conformance statement over a bundle, and the document a reader is handed.

Every finding is read from the bundle. Nothing here recomputes a rate, a bound or a grade:
`estimates.json` and `scorecard.json` hold those, they were computed once where the working
can be checked, and a second implementation sitting in the one output nobody thinks to
re-check is how two numbers for the same thing get published.

A statement that lists only what passed is marketing. The findings below return `not met`
for the practice items this tool does not yet satisfy, and the example bundle produces
several of them.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from touchstone import __version__, document
from touchstone import bundle as bundle_files
from touchstone.contracts.estimates import Estimates
from touchstone.contracts.lock import PlanLock
from touchstone.contracts.report import Finding, Report
from touchstone.contracts.scorecard import Scorecard
from touchstone.errors import BundleError
from touchstone.estimate import ESTIMATES_NAME
from touchstone.freeze import LOCK_NAME

PROFILE = "nist-ai-800-2"
SOURCE = "NIST AI 800-2 ipd, Practices 3.1 to 3.3. doi:10.6028/NIST.AI.800-2.ipd"

ITEMS_NAME = "items.jsonl"
SCORECARD_NAME = "scorecard.json"


def _count(number: int, noun: str) -> str:
    """`1 image`, `2 images`. A report that says `1 image(s)` was written by something that
    did not expect to be read."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _read(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"{path}: {exc}") from exc
    return loaded if isinstance(loaded, dict) else None


@dataclass
class Contents:
    """What a bundle holds, loaded once. Every part is optional, because a directory that
    was never graded is a bundle the statement has to describe rather than refuse."""

    estimates: Estimates | None
    scorecard: Scorecard | None
    lock: PlanLock | None
    manifest: dict[str, object] | None


def load(bundle_dir: Path) -> Contents:
    estimates_raw = _read(bundle_dir / ESTIMATES_NAME)
    scorecard_raw = _read(bundle_dir / SCORECARD_NAME)
    lock_raw = _read(bundle_dir / LOCK_NAME)
    return Contents(
        estimates=Estimates.model_validate(estimates_raw) if estimates_raw else None,
        scorecard=Scorecard.model_validate(scorecard_raw) if scorecard_raw else None,
        lock=PlanLock.model_validate(lock_raw) if lock_raw else None,
        manifest=_read(bundle_dir / bundle_files.MANIFEST_NAME),
    )


def conformance(bundle_dir: Path, contents: Contents | None = None) -> Report:
    """Apply the practice set to a bundle and return what it holds against each item."""
    held = contents if contents is not None else load(bundle_dir)
    estimates, scorecard, lock, manifest_raw = (
        held.estimates,
        held.scorecard,
        held.lock,
        held.manifest,
    )

    verified: bool | None = None
    if manifest_raw is not None:
        verified = not bundle_files.verify(bundle_dir)

    plan_hash = None
    if scorecard is not None:
        plan_hash = scorecard.plan_sha256
    if plan_hash is None:
        stamped = bundle_dir / "PLAN.sha256"
        if stamped.is_file():
            plan_hash = stamped.read_text(encoding="utf-8").split()[0]

    def recorded(key: str) -> str | None:
        value = manifest_raw.get(key) if manifest_raw else None
        return value if isinstance(value, str) else None

    return Report(
        touchstone_version=__version__,
        profile=PROFILE,
        source=SOURCE,
        bundle=str(bundle_dir),
        bundle_sha256=recorded("sha256"),
        plan_sha256=plan_hash,
        sealed_utc=recorded("sealed_utc"),
        access_tier=lock.access_tier if lock else (scorecard.access_tier if scorecard else None),
        verified=verified,
        findings=[
            _uncertainty(estimates),
            _variation(estimates),
            _item_results(bundle_dir, manifest_raw),
            _costs(),
            _code_and_image(lock),
            _claims_qualified(scorecard),
            _estimand(estimates),
            _assumption_checks(),
            _constructs(estimates),
            _paired_difference(scorecard),
        ],
    )


def _uncertainty(estimates: Estimates | None) -> Finding:
    if estimates is None or not estimates.estimates:
        return Finding(
            code="uncertainty_reported",
            practice="3.1.3",
            requirement="Every reported figure carries an interval and names the method",
            status="not met",
            detail=f"the bundle holds no {ESTIMATES_NAME}, so there is no figure to qualify",
        )
    methods = sorted({estimate.estimator for estimate in estimates.estimates})
    confidence = {
        float(estimate.parameters["confidence"])
        for estimate in estimates.estimates
        if isinstance(estimate.parameters.get("confidence"), int | float)
    }
    level = f"{confidence.pop():.0%} " if len(confidence) == 1 else ""
    return Finding(
        code="uncertainty_reported",
        practice="3.1.3",
        requirement="Every reported figure carries an interval and names the method",
        status="met",
        detail=(
            f"{len(estimates.estimates)} figures, each with a {level}interval, its denominator "
            f"and the parameters the estimator used. Methods: {', '.join(methods)}"
        ),
        evidence=[ESTIMATES_NAME],
    )


def _variation(estimates: Estimates | None) -> Finding:
    requirement = "Sources of variation are decomposed, or named as unquantified"
    if estimates is None or not estimates.replicate_variance:
        return Finding(
            code="variation_decomposed",
            practice="3.1.4",
            requirement=requirement,
            status="not met",
            detail=(
                "the run holds one replicate per item, so between-replicate variance was "
                "never measured and the interval reflects sampling error alone"
            ),
            evidence=[ESTIMATES_NAME] if estimates else [],
        )
    return Finding(
        code="variation_decomposed",
        practice="3.1.4",
        requirement=requirement,
        status="met",
        detail=(
            f"{_count(len(estimates.replicate_variance), 'outcome')} split into variance "
            "from sampling completions and from sampling items. Three sources are named "
            "unquantified: item selection against deployment, judge error, and item leakage"
        ),
        evidence=[ESTIMATES_NAME],
    )


def _item_results(bundle_dir: Path, manifest: dict[str, object] | None) -> Finding:
    requirement = "Item-level results are present, not only aggregates"
    path = bundle_dir / ITEMS_NAME
    if not path.is_file():
        return Finding(
            code="item_results",
            practice="3.2.2",
            requirement=requirement,
            status="not met",
            detail=f"the bundle holds no {ITEMS_NAME}, so no figure in it can be recomputed",
        )
    rows = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    sealed = ""
    if manifest is not None:
        listed = manifest.get("files")
        recorded = {
            entry["path"]
            for entry in (listed if isinstance(listed, list) else [])
            if isinstance(entry, dict)
        }
        sealed = " and hashed in the manifest" if ITEMS_NAME in recorded else " and not hashed"
    return Finding(
        code="item_results",
        practice="3.2.2",
        requirement=requirement,
        status="met",
        detail=f"{rows} item records, one row per item{sealed}",
        evidence=[ITEMS_NAME],
    )


def _costs() -> Finding:
    return Finding(
        code="costs_recorded",
        practice="3.2.3",
        requirement="The cost of producing the result is recorded",
        status="not met",
        detail=(
            "nothing in the bundle records tokens, wall time or spend. A reader cannot tell "
            "what a wider interval would have cost to buy"
        ),
    )


def _code_and_image(lock: PlanLock | None) -> Finding:
    requirement = "The evaluation code and the image that ran are identified and obtainable"
    if lock is None or not lock.packs:
        return Finding(
            code="code_and_image",
            practice="3.2.5",
            requirement=requirement,
            status="not met",
            detail=f"the bundle holds no {LOCK_NAME}, so nothing names what ran",
        )
    unpublished = [pack.id for pack in lock.packs if "/" not in pack.image.split("@")[0]]
    if unpublished:
        return Finding(
            code="code_and_image",
            practice="3.2.5",
            requirement=requirement,
            status="not met",
            detail=(
                f"{_count(len(lock.packs), 'image')} pinned by digest, and "
                f"{', '.join(unpublished)} "
                "names no registry, so a reader holding this bundle cannot pull what ran"
            ),
            evidence=[LOCK_NAME],
        )
    return Finding(
        code="code_and_image",
        practice="3.2.5",
        requirement=requirement,
        status="met",
        detail=f"{_count(len(lock.packs), 'image')} pinned to a registry digest, named in the lock",
        evidence=[LOCK_NAME],
    )


def _claims_qualified(scorecard: Scorecard | None) -> Finding:
    requirement = "Claims are qualified by what the evidence supports"
    if scorecard is None:
        return Finding(
            code="claims_qualified",
            practice="3.3",
            requirement=requirement,
            status="not applicable",
            detail="the bundle carries no grades, so it makes no claim to qualify",
        )
    verdicts = [indicator.verdict for indicator in scorecard.indicators]
    capped = [indicator.id for indicator in scorecard.indicators if indicator.ceiling]
    straddling = verdicts.count("indeterminate")
    return Finding(
        code="claims_qualified",
        practice="3.3",
        requirement=requirement,
        status="met",
        detail=(
            f"{len(verdicts)} indicators at access tier {scorecard.access_tier}. "
            f"{straddling} returned indeterminate where the interval spans a boundary, "
            f"{verdicts.count('ungraded')} ungraded, and {len(capped)} capped by a ceiling"
        ),
        evidence=[SCORECARD_NAME],
    )


def _estimand(estimates: Estimates | None) -> Finding:
    requirement = "Each interval names the estimand it covers and the source of the method"
    if estimates is None or not estimates.estimates:
        return Finding(
            code="estimand_named",
            requirement=requirement,
            status="not met",
            detail="there are no figures to name an estimand for",
        )
    unnamed = [
        estimate.metric for estimate in estimates.estimates if not estimate.reference.strip()
    ]
    if unnamed:
        return Finding(
            code="estimand_named",
            requirement=requirement,
            status="not met",
            detail=f"{len(unnamed)} figure(s) carry no citation for the estimator used",
            evidence=[ESTIMATES_NAME],
        )
    return Finding(
        code="estimand_named",
        requirement=requirement,
        status="met",
        detail=(
            "every figure carries its estimator, the parameters it used and a published "
            "citation for the method, so the arithmetic can be redone elsewhere"
        ),
        evidence=[ESTIMATES_NAME],
    )


def _assumption_checks() -> Finding:
    return Finding(
        code="assumption_checks",
        requirement="The checks behind each estimator's assumptions are recorded",
        status="not met",
        detail=(
            "the bundle records which estimator ran and not whether its assumptions hold. "
            "A Wilson interval on a sample that is not exchangeable is arithmetic on the "
            "wrong model, and nothing here would say so"
        ),
    )


def _constructs(estimates: Estimates | None) -> Finding:
    requirement = "Figures from packs measuring different things are not aggregated"
    if estimates is None:
        return Finding(
            code="constructs_separated",
            requirement=requirement,
            status="not met",
            detail=f"the bundle holds no {ESTIMATES_NAME}",
        )
    if estimates.pooled:
        return Finding(
            code="constructs_separated",
            requirement=requirement,
            status="not met",
            detail=(
                f"{len(estimates.packs)} packs contributed and the figures carrying no pack "
                "pool them. Two packs reporting the same outcome key are not measuring the "
                "same construct"
            ),
            evidence=[ESTIMATES_NAME],
        )
    return Finding(
        code="constructs_separated",
        requirement=requirement,
        status="met",
        detail=(
            "one pack contributed, so every figure names what produced it and nothing is "
            "pooled across constructs"
        ),
        evidence=[ESTIMATES_NAME],
    )


def _paired_difference(scorecard: Scorecard | None) -> Finding:
    requirement = "Movement against an earlier evaluation is estimated as a paired difference"
    if scorecard is None or scorecard.prior_plan_sha256 is None:
        return Finding(
            code="paired_difference",
            requirement=requirement,
            status="not applicable",
            detail="this bundle was not compared against an earlier one",
        )
    return Finding(
        code="paired_difference",
        requirement=requirement,
        status="not met",
        detail=(
            "movement is graded from two independent intervals rather than from the "
            "difference and its own interval, which is wider than either and is the figure "
            "a claim about drift needs"
        ),
        evidence=[SCORECARD_NAME],
    )


def write(bundle_dir: Path, out: Path) -> Report:
    """Build the statement and set it as a PDF at `out`.

    Refuses to write inside the bundle. A file that appears in a sealed directory is a file
    the manifest does not record, and `verify` would then report the report as tampering.
    """
    if out.resolve().parent == bundle_dir.resolve():
        raise BundleError(
            f"{out} is inside {bundle_dir}. A file the manifest does not record makes the "
            "bundle fail its own verification, so write the statement beside it"
        )
    held = load(bundle_dir)
    report = conformance(bundle_dir, held)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(document.build(report, held.estimates, held.scorecard))
    return report


def lines(report: Report) -> list[str]:
    """The findings, one per line, for somebody at a terminal."""
    return [
        f"  {finding.status:>15}  {finding.practice or 'added':>7}  {finding.requirement}"
        for finding in report.findings
    ]
