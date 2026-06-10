"""Scenario pack pipeline: validated market data in, runnable scenarios out.

A pack bundles three artifacts in one directory:

- ``scenarios.json``: the generated scenario records with BATNA derivations.
- ``experiment_config.json``: a ready-to-run ``opennego.experiment.v1`` config
  whose scenario entries pin the generated constraints, so ``opennego run``
  executes the pack without runner changes.
- ``pack_manifest.json``: ``opennego.scenario_pack.v1`` provenance — source
  file fingerprints, generator seed and settings, and category coverage.

Packs are deterministic: the same inputs and seed produce identical bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import read_json, to_jsonable, write_json
from opennego.market_validation import validate_market_dataset
from opennego.scenario_generator import (
    GeneratorSettings,
    ScenarioGenerationError,
    generate_scenarios,
    load_products,
)
from opennego.schema import Scenario

SCENARIO_PACK_SCHEMA_VERSION = "opennego.scenario_pack.v1"


class ScenarioPackError(ValueError):
    """Raised when a scenario pack cannot be built."""


@dataclass(frozen=True)
class ScenarioPackSummary:
    schema_version: str
    name: str
    output_dir: str
    seed: int
    scenario_count: int
    categories: tuple[str, ...]
    scenarios_file: str
    experiment_config_file: str
    manifest_file: str


@dataclass(frozen=True)
class ScenarioPackValidationResult:
    schema_version: str
    status: str
    manifest_file: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def build_scenario_pack(
    *,
    products_file: str | Path,
    market_comps_file: str | Path,
    output_dir: str | Path,
    seed: int,
    scenarios_per_product: int = 1,
    max_turns: int = 8,
    name: str | None = None,
    dataset_manifest_file: str | Path | None = None,
    settings: GeneratorSettings | None = None,
) -> ScenarioPackSummary:
    validation = validate_market_dataset(
        products_file=products_file,
        market_comps_file=market_comps_file,
        manifest_file=dataset_manifest_file,
    )
    if validation.status != "passed":
        raise ScenarioPackError(
            "market dataset failed validation: " + "; ".join(validation.errors)
        )

    settings = settings or GeneratorSettings(max_turns=max_turns)
    if settings.max_turns != max_turns:
        settings = GeneratorSettings(
            buyer_friction_range=settings.buyer_friction_range,
            seller_patience_range=settings.seller_patience_range,
            seller_relist_cost_range=settings.seller_relist_cost_range,
            seller_floor_fraction=settings.seller_floor_fraction,
            max_turns=max_turns,
        )

    try:
        products = load_products(products_file)
        scenarios = generate_scenarios(
            products,
            seed=seed,
            scenarios_per_product=scenarios_per_product,
            settings=settings,
        )
    except ScenarioGenerationError as exc:
        raise ScenarioPackError(str(exc)) from exc

    pack_name = name or f"scenario_pack_s{seed}"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    scenarios_file = output / "scenarios.json"
    config_file = output / "experiment_config.json"
    manifest_file = output / "pack_manifest.json"

    write_json(scenarios_file, to_jsonable(list(scenarios)))
    config = _experiment_config(
        pack_name=pack_name,
        products_file=str(products_file),
        market_comps_file=str(market_comps_file),
        scenarios=scenarios,
        seed=seed,
    )
    write_json(config_file, config)

    categories = _categories(scenarios)
    manifest = {
        "schema_version": SCENARIO_PACK_SCHEMA_VERSION,
        "name": pack_name,
        "seed": seed,
        "scenarios_per_product": scenarios_per_product,
        "scenario_count": len(scenarios),
        "categories": list(categories),
        "generator_settings": to_jsonable(settings),
        "sources": {
            "products_file": _source_record(products_file),
            "market_comps_file": _source_record(market_comps_file),
            **(
                {"dataset_manifest_file": _source_record(dataset_manifest_file)}
                if dataset_manifest_file is not None
                else {}
            ),
        },
        "artifacts": {
            "scenarios": scenarios_file.name,
            "experiment_config": config_file.name,
        },
        "market_validation_status": validation.status,
    }
    write_json(manifest_file, manifest)

    return ScenarioPackSummary(
        schema_version=SCENARIO_PACK_SCHEMA_VERSION,
        name=pack_name,
        output_dir=str(output),
        seed=seed,
        scenario_count=len(scenarios),
        categories=categories,
        scenarios_file=str(scenarios_file),
        experiment_config_file=str(config_file),
        manifest_file=str(manifest_file),
    )


def validate_scenario_pack(manifest_file: str | Path) -> ScenarioPackValidationResult:
    manifest_path = Path(manifest_file)
    errors: list[str] = []
    warnings: list[str] = []

    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError) as exc:
        return ScenarioPackValidationResult(
            schema_version=SCENARIO_PACK_SCHEMA_VERSION,
            status="failed",
            manifest_file=str(manifest_path),
            errors=(f"manifest: cannot read JSON object: {exc}",),
            warnings=(),
        )

    if manifest.get("schema_version") != SCENARIO_PACK_SCHEMA_VERSION:
        errors.append(
            "manifest.schema_version: expected "
            f"{SCENARIO_PACK_SCHEMA_VERSION!r}, got {manifest.get('schema_version')!r}"
        )

    pack_dir = manifest_path.parent
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        errors.append("artifacts: expected object")
        artifacts = {}

    scenarios_name = artifacts.get("scenarios")
    if scenarios_name is None:
        errors.append("artifacts.scenarios: missing")
    else:
        _validate_scenarios_file(pack_dir / str(scenarios_name), manifest, errors)

    config_name = artifacts.get("experiment_config")
    if config_name is None:
        errors.append("artifacts.experiment_config: missing")
    else:
        _validate_config_file(pack_dir / str(config_name), errors, warnings)

    sources = manifest.get("sources")
    if not isinstance(sources, Mapping) or not sources:
        errors.append("sources: expected non-empty object")
    else:
        for key, record in sources.items():
            _validate_source_record(key, record, errors, warnings)

    status = "passed" if not errors else "failed"
    return ScenarioPackValidationResult(
        schema_version=SCENARIO_PACK_SCHEMA_VERSION,
        status=status,
        manifest_file=str(manifest_path),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _validate_scenarios_file(
    path: Path,
    manifest: Mapping[str, Any],
    errors: list[str],
) -> None:
    if not path.exists():
        errors.append(f"artifacts.scenarios: missing file {path}")
        return
    try:
        records = json.loads(path.read_text())
    except ValueError as exc:
        errors.append(f"artifacts.scenarios: invalid JSON: {exc}")
        return
    if not isinstance(records, list) or not records:
        errors.append("artifacts.scenarios: expected non-empty list")
        return
    expected_count = manifest.get("scenario_count")
    if isinstance(expected_count, int) and expected_count != len(records):
        errors.append(
            f"scenario_count: manifest says {expected_count}, file has {len(records)}"
        )
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            errors.append(f"scenarios[{index}]: expected object")
            continue
        budget = record.get("buyer_budget")
        reservation = record.get("seller_reservation_price")
        if not isinstance(budget, (int, float)) or budget <= 0:
            errors.append(f"scenarios[{index}].buyer_budget: expected positive number")
        if not isinstance(reservation, (int, float)) or reservation <= 0:
            errors.append(
                f"scenarios[{index}].seller_reservation_price: expected positive number"
            )
        metadata = record.get("metadata")
        if not isinstance(metadata, Mapping) or not isinstance(
            metadata.get("batna"), Mapping
        ):
            errors.append(f"scenarios[{index}].metadata.batna: missing")


def _validate_config_file(
    path: Path,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not path.exists():
        errors.append(f"artifacts.experiment_config: missing file {path}")
        return
    from opennego.runner import ConfigValidationError, load_experiment_config

    try:
        config = load_experiment_config(path)
    except ConfigValidationError as exc:
        errors.append(f"artifacts.experiment_config: {exc}")
        return
    for scenario_config in config.scenarios:
        if not scenario_config.products_file.exists():
            warnings.append(
                "experiment_config: products_file not found from current "
                f"working directory: {scenario_config.products_file}"
            )
            break


def _validate_source_record(
    key: str,
    record: Any,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(record, Mapping):
        errors.append(f"sources.{key}: expected object")
        return
    path_value = record.get("path")
    fingerprint = record.get("sha256")
    if not path_value or not fingerprint:
        errors.append(f"sources.{key}: expected path and sha256")
        return
    source_path = Path(str(path_value))
    if not source_path.exists():
        warnings.append(
            f"sources.{key}: source file not found from current working "
            f"directory: {source_path}"
        )
        return
    observed = _sha256(source_path)
    if observed != fingerprint:
        errors.append(
            f"sources.{key}: fingerprint mismatch (expected {fingerprint}, "
            f"observed {observed})"
        )


def _experiment_config(
    *,
    pack_name: str,
    products_file: str,
    market_comps_file: str,
    scenarios: Sequence[Scenario],
    seed: int,
) -> Mapping[str, Any]:
    scenario_entries = []
    for scenario in scenarios:
        scenario_entries.append(
            {
                "id": str(scenario.metadata["scenario_id"]),
                "products_file": products_file,
                "product_id": scenario.product.id,
                "buyer_budget": scenario.buyer_budget,
                "seller_reservation_price": scenario.seller_reservation_price,
                "max_turns": scenario.max_turns,
                "metadata": to_jsonable(dict(scenario.metadata)),
            }
        )
    return {
        "schema_version": "opennego.experiment.v1",
        "name": pack_name,
        "output_dir": f"runs/{pack_name}",
        "resume": False,
        "fail_fast": True,
        "metadata": {"scenario_pack": pack_name},
        "seeds": [seed],
        "agents": {
            "buyer": {"kind": "tool_aware_buyer"},
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": scenario_entries,
        "tool_regimes": [
            {"id": "no_tools", "tools": []},
            {
                "id": "buyer_private_market_search",
                "tools": [
                    {
                        "name": "market_price_search",
                        "kind": "market_price",
                        "source": market_comps_file,
                        "visibility": "buyer_private",
                        "mode": "clean",
                    }
                ],
            },
        ],
    }


def _categories(scenarios: Sequence[Scenario]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for scenario in scenarios:
        category = scenario.product.attributes.get("category", "uncategorized")
        seen.setdefault(str(category), None)
    return tuple(seen)


def _source_record(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    return {"path": str(source), "sha256": _sha256(source)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
