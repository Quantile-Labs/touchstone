from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from touchstone import __version__, bundle, plan_check
from touchstone import anchor as anchor_plan
from touchstone import estimate as estimate_items
from touchstone import freeze as freeze_plan
from touchstone import grade as grade_run
from touchstone import run as run_plan
from touchstone.backends.docker import DockerBackend
from touchstone.errors import TouchstoneError

app = typer.Typer(add_completion=False, help="Evaluation runs that produce verifiable evidence.")

NOT_YET = "not implemented yet, see the pipeline table in README.md"


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
) -> None:
    """Check a plan against the manifests of the packs it names."""
    try:
        plan = plan_check.load_plan(plan_path)
        found = {
            path.parent.name: plan_check.load_manifest(path)
            for path in sorted(manifests.glob("*/manifest.yaml"))
        }
        problems = plan_check.check(plan, found)
    except TouchstoneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if problems:
        typer.echo(f"{plan_path}: {len(problems)} problem(s)", err=True)
        for problem in problems:
            typer.echo(f"  {problem}", err=True)
        raise typer.Exit(1)

    typer.echo(f"{plan_path}: ok, {len(plan.packs)} pack(s)")


@app.command()
def verify(
    bundle_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
) -> None:
    """Re-check every file in a bundle against its recorded hash. Offline."""
    try:
        failures = bundle.verify(bundle_dir)
    except TouchstoneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if failures:
        typer.echo(f"{bundle_dir}: {len(failures)} failure(s)", err=True)
        for failure in failures:
            typer.echo(f"  {failure}", err=True)
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
            help="Run packs that declare egress on a backend that cannot enforce it. "
            "They get the whole network and the bundle records that they did",
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
        typer.Option("--by", "-b", help="Stratum key to group by. Repeat to cross keys"),
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
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"{path}: {len(estimates.estimates)} estimate(s) from {estimates.items} item(s)")
    for line in estimate_items.lines(estimates):
        typer.echo(line)

    if estimates.pooled:
        typer.echo(
            f"{len(estimates.packs)} packs contributed: {', '.join(estimates.packs)}. Lines "
            "without a pack pool them, and packs reporting the same outcome are not "
            "measuring the same thing. Quote the per-pack lines",
            err=True,
        )


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
) -> None:
    """Apply a score card and produce DQI indicators. Offline, no Docker."""
    try:
        card = grade_run.load_scorecard(score_card)
        estimates = grade_run.load_estimates(run_dir)

        problems = grade_run.check(card, estimates)
        if problems:
            for problem in problems:
                typer.echo(problem, err=True)
            raise typer.Exit(1)

        scorecard = grade_run.grade(
            card,
            estimates,
            grade_run.access_tier(run_dir),
            grade_run.summary_only_packs(run_dir),
            grade_run.plan_hash(run_dir),
        )
        path = grade_run.write_scorecard(scorecard, run_dir)
    except TouchstoneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    counted = Counter(indicator.verdict for indicator in scorecard.indicators)
    typer.echo(
        f"{path}: {len(scorecard.indicators)} indicator(s) at access tier {scorecard.access_tier}"
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
