# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Validate a plan against the manifests of the packs it names.

The JSON Schemas in `docs/schemas/` cover the shape of a plan, which an editor checks as
it is typed. What is left here is everything a schema cannot see, because it needs the
pack manifests as well as the plan: a pack with no manifest, a system or a parameter the
plan passes that the pack never declared, and a required one it left out.
"""

from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from touchstone import positions
from touchstone.contracts import Manifest, Plan
from touchstone.contracts.diagnostics import Problem
from touchstone.errors import PlanError


def load_plan(path: Path) -> Plan:
    try:
        return Plan.model_validate(yaml.safe_load(path.read_text()))
    except (yaml.YAMLError, ValidationError) as exc:
        raise PlanError(f"{path}: {exc}") from exc


def load_manifest(path: Path) -> Manifest:
    try:
        return Manifest.model_validate(yaml.safe_load(path.read_text()))
    except (yaml.YAMLError, ValidationError) as exc:
        raise PlanError(f"{path}: {exc}") from exc


PACKS_DIR = "packs"


def find_manifests(plan_path: Path) -> Path | None:
    """The pack directory a plan means when none is named: `packs/` in the current
    directory, else the nearest `packs/` at or above the plan. None where there is neither.

    The plan's own location is searched so that `validate` works from wherever it is typed,
    and the current directory comes first so that an explicit layout is never overridden
    by one found further up.
    """
    candidates = [Path(PACKS_DIR), *(parent / PACKS_DIR for parent in plan_path.resolve().parents)]
    found = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if found is None or not found.is_absolute():
        return found
    try:
        return found.relative_to(Path.cwd())
    except ValueError:
        return found


def check(
    plan: Plan,
    manifests: dict[str, Manifest],
    plan_path: Path | None = None,
    manifests_dir: Path | None = None,
) -> list[Problem]:
    """Cross-check the plan against pack manifests. Returns every problem, not the first.

    `plan_path` is what turns a problem into something an editor can point at. Without it
    the problems are the same problems and carry no position, which is what a caller that
    holds a `Plan` and not the file it came from can honestly report. `manifests_dir` lets
    a missing manifest name the file that was expected.
    """
    source = positions.load_source(plan_path) if plan_path is not None else None
    where = str(plan_path) if plan_path is not None else None

    problems: list[Problem] = []
    seen = set()

    def report(
        code: str, pack_id: str, message: str, *candidates: Sequence[positions.Step]
    ) -> None:
        at = positions.first(source, *candidates) if candidates else None
        problems.append(
            Problem(
                code=code,
                message=f"{pack_id}: {message}",
                path=where,
                line=at[0] if at else None,
                column=at[1] if at else None,
                subject=pack_id,
            )
        )

    for index, pack in enumerate(plan.packs):
        at_pack: Sequence[positions.Step] = ("packs", index)

        if pack.id in seen:
            report("duplicate_pack_id", pack.id, "duplicate pack id", (*at_pack, "id"), at_pack)
        seen.add(pack.id)

        manifest = manifests.get(pack.id)
        if manifest is None:
            expected = (
                f"no manifest at {manifests_dir / pack.id / 'manifest.yaml'}"
                if manifests_dir is not None
                else "no manifest found"
            )
            report("pack_manifest_missing", pack.id, expected, (*at_pack, "id"), at_pack)
            continue

        for system in manifest.input_systems:
            if system.required and system.name not in pack.systems:
                report(
                    "system_missing",
                    pack.id,
                    f"missing required system '{system.name}'",
                    (*at_pack, "systems"),
                    at_pack,
                )

        for slot, name in pack.systems.items():
            if name not in plan.systems:
                report(
                    "system_undefined",
                    pack.id,
                    f"system '{name}' is not defined in the plan",
                    (*at_pack, "systems", slot),
                    (*at_pack, "systems"),
                    at_pack,
                )

        accepted = {parameter.name for parameter in manifest.input_schema}
        for name in pack.params:
            if name not in accepted:
                report(
                    "parameter_unknown",
                    pack.id,
                    f"pack does not accept parameter '{name}'",
                    (*at_pack, "params", name),
                    (*at_pack, "params"),
                    at_pack,
                )

        for parameter in manifest.input_schema:
            if parameter.required and parameter.name not in pack.params:
                report(
                    "parameter_missing",
                    pack.id,
                    f"missing required parameter '{parameter.name}'",
                    (*at_pack, "params"),
                    at_pack,
                )

    return problems
