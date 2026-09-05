"""Every contract refuses a key it does not know, at every level of nesting.

`docs/reference/contracts.md` tells a reader that an unknown key raises rather than being
quietly dropped, and a reader writing a plan relies on it: a misspelled `replicats` that is
silently ignored runs the pack once, reports a rate with no replicate variance beside it,
and looks exactly like a plan that asked for one replicate on purpose. Six nested models
used to accept anything, so the promise held at the top of a plan and nowhere inside it.

The sweep is over every model in the package rather than a list kept by hand, because the
promise is about the contracts as a set and a model added later inherits it.
"""

import importlib
import pkgutil
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

import touchstone.contracts
from touchstone.contracts import Manifest, Plan
from touchstone.plan_check import load_manifest, load_plan

PLAN = {
    "plan_name": "demo",
    "access_tier": "black_box",
    "systems": {"chatbot": {"type": "llm_api"}},
    "packs": [
        {
            "id": "example_pack",
            "image": "example/example_pack:1.0",
            "systems": {"system_under_test": "chatbot"},
            "params": {"max_items": 50},
            "replicates": 2,
        }
    ],
}

MANIFEST = {
    "name": "example_pack",
    "version": "1.0",
    "input_systems": [{"name": "system_under_test", "type": "llm_api"}],
    "input_schema": [{"name": "max_items", "type": "integer"}],
    "strata": [{"name": "language", "values": ["en", "yo"]}],
    "network": {"egress": []},
}


def _models() -> list[type[BaseModel]]:
    """Every model in `touchstone.contracts`, found rather than listed, so a contract added
    later is covered without anybody remembering to add it here."""
    found: dict[str, type[BaseModel]] = {}
    for module in pkgutil.iter_modules(touchstone.contracts.__path__):
        loaded = importlib.import_module(f"touchstone.contracts.{module.name}")
        for name, value in vars(loaded).items():
            if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel:
                found[f"{value.__module__}.{name}"] = value
    return [found[key] for key in sorted(found)]


def test_every_contract_model_forbids_extra_keys():
    lax = [
        f"{model.__module__}.{model.__name__}"
        for model in _models()
        if model.model_config.get("extra") != "forbid"
    ]
    assert not lax, "extra keys are accepted by:\n" + "\n".join(lax)


def test_a_typo_inside_a_pack_entry_is_rejected():
    """The one this was written for. `replicates` is the field most worth misspelling,
    because getting it wrong costs a replicate variance nobody notices is missing."""
    pack = {key: value for key, value in PLAN["packs"][0].items() if key != "replicates"}
    with pytest.raises(ValidationError, match="replicats"):
        Plan.model_validate(PLAN | {"packs": [pack | {"replicats": 2}]})


def test_a_typo_inside_a_system_entry_is_rejected():
    with pytest.raises(ValidationError, match="parms"):
        Plan.model_validate(PLAN | {"systems": {"chatbot": {"type": "llm_api", "parms": {}}}})


def test_a_typo_in_a_declared_input_system_is_rejected():
    unknown = [{"name": "system_under_test", "type": "llm_api", "requird": True}]
    with pytest.raises(ValidationError, match="requird"):
        Manifest.model_validate(MANIFEST | {"input_systems": unknown})


def test_a_typo_in_a_declared_parameter_is_rejected():
    with pytest.raises(ValidationError, match="typ"):
        Manifest.model_validate(MANIFEST | {"input_schema": [{"name": "max_items", "typ": "int"}]})


def test_a_typo_in_a_stratum_is_rejected():
    with pytest.raises(ValidationError, match="value"):
        Manifest.model_validate(MANIFEST | {"strata": [{"name": "language", "value": ["en"]}]})


def test_a_typo_in_the_egress_declaration_is_rejected():
    """The one with teeth. A pack that means `egress` and writes `egres` declares no hosts,
    which is a pack that silently gets no network rather than the hosts it needs."""
    with pytest.raises(ValidationError, match="egres"):
        Manifest.model_validate(MANIFEST | {"network": {"egres": ["api.example.com"]}})


def test_the_plans_and_manifests_this_repository_ships_still_load():
    """Tightening a model is only safe while the files here still pass it."""
    repo = Path(__file__).resolve().parents[1]
    assert load_plan(repo / "examples" / "plan.yaml").packs
    assert load_manifest(repo / "packs" / "example_pack" / "manifest.yaml").name == "example_pack"
