"""Execute a frozen plan and record what happened while it happens.

The ledger is written by this module at the moment of each event, not assembled at the
end. 02-DESIGN.md section 6 rule 2: a run log a person writes afterwards is a discipline,
and the discipline failed twice.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from touchstone.backends.base import ContainerBackend, RunSpec
from touchstone.contracts.lock import PlanLock
from touchstone.errors import TouchstoneError
from touchstone.freeze import LOCK_NAME, check_frozen, load_lock, recorded_hash

ITEMS_NAME = "items.jsonl"
LEDGER_DIR = "ledger"
RUNLOG_NAME = "RUNLOG.jsonl"
RUNS_DIR = "runs"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    """Append-only. Every line is flushed before the next thing happens."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def record(self, event: str, **fields) -> None:
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
    params: dict
    systems: dict[str, str]

    @property
    def run_id(self) -> str:
        return f"{self.pack_id}-{self.replicate}"


def units(lock: PlanLock) -> list[Unit]:
    return [
        Unit(pack.id, replicate, pack.image, seed, pack.params, pack.systems)
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


def collect_items(out_dir: Path) -> int:
    """Concatenate every unit's records into one items.jsonl. Returns the line count."""
    lines = []
    for path in sorted((out_dir / RUNS_DIR).glob(f"*/{ITEMS_NAME}")):
        lines.extend(path.read_text().splitlines())
    (out_dir / ITEMS_NAME).write_text("".join(line + "\n" for line in lines))
    return len(lines)


def run(lock_dir: Path, out_dir: Path, backend: ContainerBackend) -> list[str]:
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
    for unit in todo:
        ledger.record("unit_started", run_id=unit.run_id, image=unit.image, seed=unit.seed)
        spec = RunSpec(
            run_id=unit.run_id,
            pack_id=unit.pack_id,
            replicate=unit.replicate,
            image=unit.image,
            args=_args(unit, lock),
            output_dir=out_dir / RUNS_DIR / unit.run_id,
        )
        try:
            result = backend.run(spec)
        except TouchstoneError as exc:
            ledger.record("unit_failed", run_id=unit.run_id, error=str(exc))
            failures.append(f"{unit.run_id}: {exc}")
            continue

        ledger.record(
            "unit_finished",
            run_id=unit.run_id,
            exit_code=result.exit_code,
            image_digest=result.image_digest,
            termination=result.termination,
        )
        if result.exit_code != 0:
            reason = result.termination or f"exit {result.exit_code}"
            failures.append(f"{unit.run_id}: {reason}")

    count = collect_items(out_dir)
    ledger.record("run_finished", items=count, failures=len(failures))
    return failures
