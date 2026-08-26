"""Execute a frozen plan and record what happened while it happens.

The ledger is written by this module at the moment of each event, not assembled at the
end. 02-DESIGN.md section 6 rule 2: a run log a person writes afterwards is a discipline,
and the discipline failed twice.
"""

import json
import platform
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from touchstone import __version__
from touchstone.backends.base import ContainerBackend, RunResult, RunSpec
from touchstone.contracts import Environment
from touchstone.contracts.bundle import LEDGER_DIR, RUN_FINISHED, RUNLOG_NAME
from touchstone.contracts.lock import PlanLock
from touchstone.contracts.manifest import Resources
from touchstone.errors import TouchstoneError
from touchstone.freeze import HASH_NAME, LOCK_NAME, check_frozen, load_lock, recorded_hash

ENVIRONMENT_NAME = "environment.json"
ITEMS_NAME = "items.jsonl"
RUNS_DIR = "runs"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    """Append-only. Every line is flushed before the next thing happens."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def record(self, event: str, **fields: Any) -> None:
        line = json.dumps({"utc": _now(), "event": event, **fields}, sort_keys=True)
        with self.path.open("a") as handle:
            handle.write(line + "\n")
            handle.flush()


@dataclass
class Unit:
    """One pack at one replicate. The thing that either ran or did not."""

    pack_id: str
    replicate: int
    image: str
    seed: int
    params: dict[str, Any]
    systems: dict[str, str]
    egress: list[str]
    resources: Resources

    @property
    def run_id(self) -> str:
        return f"{self.pack_id}-{self.replicate}"


def units(lock: PlanLock) -> list[Unit]:
    return [
        Unit(
            pack.id,
            replicate,
            pack.image,
            seed,
            pack.params,
            pack.systems,
            pack.egress,
            pack.resources,
        )
        for pack in lock.packs
        for replicate, seed in enumerate(pack.seeds)
    ]


def _args(unit: Unit, lock: PlanLock) -> list[str]:
    """The seed and the replicate are injected by the harness, never by the plan."""
    systems = {role: lock.systems[name].model_dump() for role, name in unit.systems.items()}
    params = dict(unit.params) | {"seed": unit.seed, "replicate": unit.replicate}
    return [
        "--systems-params",
        json.dumps(systems, sort_keys=True),
        "--test-params",
        json.dumps(params, sort_keys=True),
    ]


def collect_items(out_dir: Path, owners: dict[str, str]) -> tuple[int, int]:
    """Merge every unit's records into one items.jsonl, stamping which pack wrote each.

    Returns (records, overwritten). `owners` maps a run id to the pack that produced it,
    so provenance comes from the harness rather than from a directory name a pack could
    influence. A pack that stamped the field itself has its value replaced: one that could
    name itself could name another, and every rate downstream is grouped by this field.
    """
    lines = []
    overwritten = 0
    for path in sorted((out_dir / RUNS_DIR).glob(f"*/{ITEMS_NAME}")):
        pack_id = owners.get(path.parent.name)
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("pack_id") not in (None, pack_id):
                overwritten += 1
            record["pack_id"] = pack_id
            lines.append(json.dumps(record, sort_keys=True))
    (out_dir / ITEMS_NAME).write_text("".join(line + "\n" for line in lines))
    return len(lines), overwritten


def copy_plan(lock_dir: Path, out_dir: Path) -> None:
    """Put the frozen plan and its hash in the run, because the bundle has to hold them.

    02-DESIGN.md section 6: the bundle is a directory readable in 2035 by someone without
    the tool. A run whose plan lives somewhere else is not that.

    Freezing and running into one directory is the sequence the README walks through, and
    there the plan is already where it has to be. Copying a file onto itself raises, and
    this runs after the packs have, so the failure landed on a directory holding a
    finished run and cost the whole thing.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (LOCK_NAME, HASH_NAME):
        source, destination = lock_dir / name, out_dir / name
        if source.resolve() == destination.resolve():
            continue
        shutil.copyfile(source, destination)


def _overall_egress(results: list[RunResult]) -> bool | None:
    """One unit granted an unenforced network weakens the whole run's claim."""
    reported = [result.egress_enforced for result in results if result.egress_enforced is not None]
    if not reported:
        return None
    return all(reported)


def write_environment(
    out_dir: Path,
    backend: ContainerBackend,
    plan_hash: str,
    results: list[RunResult],
) -> None:
    environment = Environment(
        touchstone_version=__version__,
        python=sys.version.split()[0],
        platform=platform.platform(),
        backend=backend.name,
        isolation=backend.isolation,
        plan_hash=plan_hash,
        image_digests=sorted({result.image_digest for result in results}),
        egress_enforced=_overall_egress(results),
    )
    (out_dir / ENVIRONMENT_NAME).write_text(
        json.dumps(environment.model_dump(), indent=2, sort_keys=True) + "\n"
    )


def run(
    lock_dir: Path,
    out_dir: Path,
    backend: ContainerBackend,
    allow_unenforced_egress: bool = False,
) -> list[str]:
    """Run every unit in the frozen plan. Returns the list of failures."""
    check_frozen(lock_dir)
    lock = load_lock(lock_dir / LOCK_NAME)
    plan_hash = recorded_hash(lock_dir)

    ledger = Ledger(out_dir / LEDGER_DIR / RUNLOG_NAME)
    todo = units(lock)
    ledger.record(
        "run_started",
        plan_hash=plan_hash,
        plan_name=lock.plan_name,
        access_tier=lock.access_tier,
        backend=backend.name,
        isolation=backend.isolation,
        units=len(todo),
    )

    failures = []
    results: list[RunResult] = []
    for unit in todo:
        ledger.record("unit_started", run_id=unit.run_id, image=unit.image, seed=unit.seed)
        spec = RunSpec(
            run_id=unit.run_id,
            pack_id=unit.pack_id,
            replicate=unit.replicate,
            image=unit.image,
            args=_args(unit, lock),
            output_dir=out_dir / RUNS_DIR / unit.run_id,
            egress=unit.egress,
            resources=unit.resources,
            allow_unenforced_egress=allow_unenforced_egress,
        )
        try:
            result = backend.run(spec)
        except TouchstoneError as exc:
            ledger.record("unit_failed", run_id=unit.run_id, error=str(exc))
            failures.append(f"{unit.run_id}: {exc}")
            continue

        results.append(result)
        ledger.record(
            "unit_finished",
            run_id=unit.run_id,
            exit_code=result.exit_code,
            image_digest=result.image_digest,
            termination=result.termination,
            egress_enforced=result.egress_enforced,
        )
        if result.exit_code != 0:
            reason = result.termination or f"exit {result.exit_code}"
            failures.append(f"{unit.run_id}: {reason}")

    owners = {unit.run_id: unit.pack_id for unit in todo}
    count, overwritten = collect_items(out_dir, owners)
    if overwritten:
        ledger.record("pack_id_overwritten", records=overwritten)
    copy_plan(lock_dir, out_dir)
    write_environment(out_dir, backend, plan_hash, results)
    ledger.record(
        RUN_FINISHED,
        items=count,
        failures=len(failures),
        egress_enforced=_overall_egress(results),
    )
    return failures
