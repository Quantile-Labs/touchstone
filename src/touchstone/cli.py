from pathlib import Path
from typing import Annotated

import typer

from touchstone import __version__, bundle, plan_check
from touchstone.errors import TouchstoneError

app = typer.Typer(add_completion=False, help="Evaluation runs that produce verifiable evidence.")

NOT_YET = "not implemented yet, see the roadmap in README.md"


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
def freeze() -> None:
    """Pin digests, hash the plan, fix seeds and thresholds."""
    _pending("freeze")


@app.command()
def run() -> None:
    """Execute packs and collect per-item observations."""
    _pending("run")


@app.command()
def estimate() -> None:
    """Compute rates and intervals, by stratum."""
    _pending("estimate")


@app.command()
def grade() -> None:
    """Apply a score card and produce DQI indicators."""
    _pending("grade")


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
