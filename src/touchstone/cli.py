# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from touchstone import __version__, bundle, errors, plan_check, positions
from touchstone import anchor as anchor_plan
from touchstone import estimate as estimate_items
from touchstone import freeze as freeze_plan
from touchstone import grade as grade_run
from touchstone import run as run_plan
from touchstone.backends.docker import DockerBackend
from touchstone.contracts.diagnostics import Envelope, Problem
from touchstone.contracts.scorecard import GradedIndicator
from touchstone.errors import TouchstoneError

app = typer.Typer(add_completion=False, help="Evaluation runs that produce verifiable evidence.")

NOT_YET = "not implemented yet, see the pipeline table in README.md"

AsJson = Annotated[
    bool,
    typer.Option(
        "--json",
        help="Write one machine-readable envelope to stdout instead of prose. The shape "
        "is Envelope in contracts/diagnostics.py, and the exit code is unchanged",
    ),
]
"""Off everywhere. A person at a terminal is the default reader and stays the default
reader; this is for whatever is reading over their shoulder."""


def _envelope(command: str, problems: list[Problem], **result: object) -> Envelope:
    return Envelope(
        touchstone_version=__version__,
        command=command,
        ok=not any(problem.severity == "error" for problem in problems),
        problems=problems,
        result=result,
    )


def _emit(envelope: Envelope) -> None:
    """Envelope to stdout, whole and on its own, so a caller can pipe the command into a
    parser without filtering the prose the commands otherwise write to both streams."""
    typer.echo(envelope.model_dump_json(indent=2))


def _straddled(indicator: GradedIndicator, card: Path, at: tuple[int, int] | None) -> Problem:
    """An indeterminate verdict, as a warning. The command succeeded and the grade is
    real, so a caller that treats this as a failure fails a run that measured what it set
    out to measure and said honestly that the interval spans a boundary."""
    return Problem(
        code="indeterminate",
        message=indicator.reason or f"{indicator.id}: indeterminate",
        severity="warning",
        subject=indicator.id,
        path=str(card),
        line=at[0] if at else None,
        column=at[1] if at else None,
    )


def _raised(command: str, exc: TouchstoneError, **result: object) -> Envelope:
    """An envelope for the one error that stopped the command. It carries no position,
    because an exception knows what went wrong and not where it was written."""
    return _envelope(command, [Problem(code=errors.code(exc), message=str(exc))], **result)


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(f"touchstone {__version__}")


@app.command()
def validate(
    plan_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    manifests: Annotated[
        Path,
        typer.Option("--manifests", "-m", help="Directory holding <pack_id>/manifest.yaml"),
    ] = Path("packs"),
    as_json: AsJson = False,
) -> None:
    """Check a plan against the manifests of the packs it names."""
    try:
        plan = plan_check.load_plan(plan_path)
        found = {
            path.parent.name: plan_check.load_manifest(path)
            for path in sorted(manifests.glob("*/manifest.yaml"))
        }
        problems = plan_check.check(plan, found, plan_path)
    except TouchstoneError as exc:
        if as_json:
            _emit(_raised("validate", exc, path=str(plan_path)))
            raise typer.Exit(1) from exc
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if as_json:
        _emit(_envelope("validate", problems, path=str(plan_path), packs=len(plan.packs)))
        if problems:
            raise typer.Exit(1)
        return

    if problems:
        typer.echo(f"{plan_path}: {len(problems)} problem(s)", err=True)
        for problem in problems:
            typer.echo(f"  {problem.message}", err=True)
        raise typer.Exit(1)

    typer.echo(f"{plan_path}: ok, {len(plan.packs)} pack(s)")


@app.command()
def verify(
    bundle_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    as_json: AsJson = False,
) -> None:
    """Re-check every file in a bundle against its recorded hash. Offline."""
    try:
        manifest = bundle.load_manifest(bundle_dir)
        failures = bundle.verify(bundle_dir)
    except TouchstoneError as exc:
        if as_json:
            _emit(_raised("verify", exc, path=str(bundle_dir)))
            raise typer.Exit(1) from exc
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if as_json:
        _emit(_envelope("verify", failures, path=str(bundle_dir), files=len(manifest.files)))
        if failures:
            raise typer.Exit(1)
        return

    if failures:
        typer.echo(f"{bundle_dir}: {len(failures)} failure(s)", err=True)
        for failure in failures:
            typer.echo(f"  {failure.message}", err=True)
        raise typer.Exit(1)

    typer.echo(f"{bundle_dir}: verified")


def _pending(name: str) -> None:
    typer.echo(f"{name}: {NOT_YET}", err=True)
    raise typer.Exit(2)


@app.command()
def freeze(
    plan_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[
        Path, typer.Option("--out", "-o", help="Where to write the lock and its hash")
    ] = Path("."),
    anchor: Annotated[
        bool, typer.Option("--anchor", help="Timestamp the hash with OpenTimestamps. Needs network")
    ] = False,
) -> None:
    """Pin every image to a digest, materialise seeds, and hash the result."""
    try:
        plan = plan_check.load_plan(plan_path)
        lock = freeze_plan.freeze(plan, DockerBackend())
        lock_path, digest = freeze_plan.write_lock(lock, out)
        receipt = anchor_plan.stamp(out / freeze_plan.HASH_NAME, out) if anchor else None
    except TouchstoneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"{lock_path}: {len(lock.packs)} pack(s) pinned")
    typer.echo(f"sha256 {digest}")
    typer.echo(f"check it with: shasum -a 256 -c {out / freeze_plan.HASH_NAME}")
    if receipt is not None:
        typer.echo(f"stamped: {receipt}. Pending until you run ots upgrade on it")


@app.command(name="run")
def run_(
    lock_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the run")],
    allow_unenforced_egress: Annotated[
        bool,
        typer.Option(
            "--allow-unenforced-egress",
            help="Downgrade: run packs that declare egress with the whole network "
            "instead of the allowlist they asked for. The docker backend enforces the "
            "allowlist without this, so passing it gives a pack more than it declared "
            "and the bundle records that it did",
        ),
    ] = False,
) -> None:
    """Execute a frozen plan. Refuses one that was never frozen or has been edited."""
    try:
        failures = run_plan.run(lock_dir, out, DockerBackend(), allow_unenforced_egress)
    except TouchstoneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if failures:
        typer.echo(f"{out}: {len(failures)} unit(s) failed", err=True)
        for failure in failures:
            typer.echo(f"  {failure}", err=True)
        raise typer.Exit(1)

    if allow_unenforced_egress:
        typer.echo(
            f"{out}: ok, with egress unenforced. environment.json records that no pack was "
            "restricted to the hosts it declared",
            err=True,
        )
        return

    typer.echo(f"{out}: ok")


@app.command()
def estimate(
    run_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    by: Annotated[
        list[str] | None,
        typer.Option(
            "--by",
            "-b",
            help="Stratum key to group by. Repeat for each key on its own and crossed",
        ),
    ] = None,
    calibrate: Annotated[
        list[str] | None,
        typer.Option(
            "--calibrate",
            "-c",
            help="Override the outcome each pack declared its confidence is a claim "
            "about. Repeat for more. Without this the frozen plan decides, and a pack "
            "that declared nothing is not calibrated at all",
        ),
    ] = None,
    seed: Annotated[
        int, typer.Option("--seed", help="Seed for the bootstrap, so its interval reproduces")
    ] = 0,
    resamples: Annotated[
        int, typer.Option("--resamples", help="Bootstrap resamples for continuous scores")
    ] = estimate_items.RESAMPLES,
    as_json: AsJson = False,
) -> None:
    """Compute rates and intervals, by stratum. Offline, no Docker."""
    try:
        items = estimate_items.load_items(run_dir)
        declared = estimate_items.declared_calibration(run_dir)
        estimates = estimate_items.estimate(
            items, by, calibrate, declared, seed=seed, resamples=resamples
        )
        path = estimate_items.write_estimates(estimates, run_dir)
    except TouchstoneError as exc:
        if as_json:
            _emit(_raised("estimate", exc, path=str(run_dir)))
            raise typer.Exit(1) from exc
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    pooled = (
        f"{len(estimates.packs)} packs contributed: {', '.join(estimates.packs)}. Lines "
        "without a pack pool them, and packs reporting the same outcome are not "
        "measuring the same thing. Quote the per-pack lines"
    )

    if as_json:
        warnings = (
            [Problem(code="packs_pooled", message=pooled, severity="warning", path=str(path))]
            if estimates.pooled
            else []
        )
        _emit(
            _envelope(
                "estimate",
                warnings,
                path=str(path),
                estimates=len(estimates.estimates),
                items=estimates.items,
                packs=list(estimates.packs),
            )
        )
        return

    typer.echo(f"{path}: {len(estimates.estimates)} estimate(s) from {estimates.items} item(s)")
    for line in estimate_items.lines(estimates):
        typer.echo(line)

    if estimates.pooled:
        typer.echo(pooled, err=True)


@app.command()
def grade(
    run_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    score_card: Annotated[
        Path,
        typer.Option(
            "--score-card",
            "-s",
            exists=True,
            dir_okay=False,
            help="The score card to apply: the ladder, its thresholds and its ceilings",
        ),
    ],
    audit: Annotated[
        Path | None,
        typer.Option(
            "--audit",
            "-a",
            exists=True,
            dir_okay=False,
            help="Responses for the indicators a person assesses rather than the bundle "
            "reports. Copied into the run, so the grade stays recomputable from it. "
            "Without this those indicators are ungraded, which is a true statement",
        ),
    ] = None,
    prior: Annotated[
        Path | None,
        typer.Option(
            "--prior",
            "-p",
            exists=True,
            file_okay=False,
            help="The bundle from the evaluation before this one, for indicators that "
            "grade movement. Without it those indicators are ungraded, which is what a "
            "first evaluation of a system honestly is",
        ),
    ] = None,
    as_json: AsJson = False,
) -> None:
    """Apply a score card and produce DQI indicators. Offline, no Docker."""
    try:
        if prior is not None and prior.resolve() == run_dir.resolve():
            circular = (
                f"{prior} is the bundle being graded. Movement measured against itself is "
                "zero by construction, which would read as a system that has not drifted"
            )
            if as_json:
                problem = Problem(code="prior_is_this_bundle", message=circular, path=str(prior))
                _emit(_envelope("grade", [problem], path=str(run_dir)))
                raise typer.Exit(1)
            typer.echo(circular, err=True)
            raise typer.Exit(1)

        card = grade_run.load_scorecard(score_card)
        estimates = grade_run.load_estimates(run_dir)
        tier = grade_run.access_tier(run_dir)
        responses = grade_run.load_audit(audit) if audit else None
        before = grade_run.load_prior(prior) if prior else None

        problems = grade_run.check(card, estimates, tier, responses, before, score_card)
        if problems:
            if as_json:
                _emit(_envelope("grade", problems, path=str(run_dir)))
                raise typer.Exit(1)
            for problem in problems:
                typer.echo(problem.message, err=True)
            raise typer.Exit(1)

        audit_sha256 = None
        if audit is not None:
            _, audit_sha256 = grade_run.copy_audit(audit, run_dir)

        scorecard = grade_run.grade(
            card,
            estimates,
            tier,
            grade_run.summary_only_packs(run_dir),
            grade_run.plan_hash(run_dir),
            responses,
            audit_sha256,
            before,
        )
        path = grade_run.write_scorecard(scorecard, run_dir)
    except TouchstoneError as exc:
        if as_json:
            _emit(_raised("grade", exc, path=str(run_dir)))
            raise typer.Exit(1) from exc
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    counted = Counter(indicator.verdict for indicator in scorecard.indicators)

    if as_json:
        source = positions.load_source(score_card)
        _emit(
            _envelope(
                "grade",
                [
                    _straddled(
                        indicator, score_card, grade_run.indicator_at(card, source, indicator.id)
                    )
                    for indicator in scorecard.indicators
                    if indicator.verdict == "indeterminate"
                ],
                path=str(path),
                indicators=len(scorecard.indicators),
                access_tier=scorecard.access_tier,
                verdicts=dict(counted),
            )
        )
        return

    typer.echo(
        f"{path}: {len(scorecard.indicators)} indicator(s) at access tier {scorecard.access_tier}"
    )
    if scorecard.audit_name:
        typer.echo(f"audit {scorecard.audit_name}, sha256 {scorecard.audit_sha256}")
    if scorecard.prior_plan_sha256 is not None:
        typer.echo(
            f"compared against {prior}, plan {scorecard.prior_plan_sha256[:8]} "
            f"against this run's {(scorecard.plan_sha256 or 'unknown')[:8]}"
        )
    for line in grade_run.lines(scorecard):
        typer.echo(line)

    if counted["indeterminate"]:
        typer.echo(
            f"{counted['indeterminate']} indicator(s) indeterminate: the interval spans a "
            "grade boundary, so the evidence does not choose between the levels shown. "
            "Reporting the better one would be a claim this run cannot support",
            err=True,
        )


@app.command(name="bundle")
def bundle_(
    bundle_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
) -> None:
    """Seal a run into an evidence bundle and hash every file."""
    try:
        manifest = bundle.seal(bundle_dir)
    except TouchstoneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"{bundle_dir}: sealed {len(manifest.files)} file(s)")
    typer.echo(f"sha256 {manifest.sha256}")

    if manifest.run_ledger == "absent":
        typer.echo(
            f"{bundle_dir} holds no run log, so this is a directory assembled by hand "
            "rather than one this tool ran. MANIFEST.json records that, and a reader is "
            "entitled to know which of the two they are holding",
            err=True,
        )
