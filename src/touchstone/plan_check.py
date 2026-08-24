"""Validate a plan against the manifests of the packs it names."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from touchstone.contracts import Manifest, Plan
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


def check(plan: Plan, manifests: dict[str, Manifest]) -> list[str]:
    """Cross-check the plan against pack manifests. Returns the list of problems."""
    problems = []
    seen = set()

    for pack in plan.packs:
        if pack.id in seen:
            problems.append(f"{pack.id}: duplicate pack id")
        seen.add(pack.id)

        manifest = manifests.get(pack.id)
        if manifest is None:
            problems.append(f"{pack.id}: no manifest found")
            continue

        for system in manifest.input_systems:
            if system.required and system.name not in pack.systems:
                problems.append(f"{pack.id}: missing required system '{system.name}'")

        for name in pack.systems.values():
            if name not in plan.systems:
                problems.append(f"{pack.id}: system '{name}' is not defined in the plan")

        accepted = {p.name for p in manifest.input_schema}
        for name in pack.params:
            if name not in accepted:
                problems.append(f"{pack.id}: pack does not accept parameter '{name}'")

        for parameter in manifest.input_schema:
            if parameter.required and parameter.name not in pack.params:
                problems.append(f"{pack.id}: missing required parameter '{parameter.name}'")

    return problems
