"""External training adapter packages for strategy configs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from opennego.artifacts import read_json, write_json
from opennego.schema import Role
from opennego.strategy_config import (
    STRATEGY_CONFIG_SCHEMA_VERSION,
    StrategyConfig,
    StrategyConfigError,
    load_strategy_config,
    prompt_layer_contract,
)

TRAINING_ADAPTER_SCHEMA_VERSION = "opennego.external_training_adapter.v1"
TRAINING_ADAPTER_VALIDATION_SCHEMA_VERSION = (
    "opennego.external_training_adapter_validation.v1"
)
SUPPORTED_INTEGRATION_MODES = frozenset({"prompt_config", "agent_factory_params"})


class TrainingAdapterError(ValueError):
    """Raised when an external training adapter package is malformed."""


@dataclass(frozen=True)
class TrainingAdapterPackage:
    schema_version: str
    adapter_id: str
    integration_mode: str
    agent_kind: str
    role: Role
    source_strategy_config: str
    strategy_config_schema_version: str
    strategy_id: str
    strategy_version: int
    prompt_layers: Mapping[str, Mapping[str, object]]
    payload: Mapping[str, Any]
    integration_contract: Mapping[str, Any]
    lineage: tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingAdapterValidationResult:
    schema_version: str
    status: str
    path: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def generate_training_adapter_package(
    strategy_config_path: str | Path,
    *,
    agent_kind: str,
    integration_mode: str = "prompt_config",
    adapter_id: str | None = None,
    entrypoint_hint: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> TrainingAdapterPackage:
    """Generate a provider-neutral adapter package from a strategy config."""

    config = load_strategy_config(strategy_config_path)
    resolved_agent_kind = _non_empty(agent_kind, "agent_kind")
    if integration_mode not in SUPPORTED_INTEGRATION_MODES:
        raise TrainingAdapterError(
            "integration_mode: expected one of "
            f"{sorted(SUPPORTED_INTEGRATION_MODES)!r}"
        )
    resolved_adapter_id = adapter_id or (
        f"{resolved_agent_kind}:{config.strategy_id}:v{config.version}"
    )
    _non_empty(resolved_adapter_id, "adapter_id")
    return TrainingAdapterPackage(
        schema_version=TRAINING_ADAPTER_SCHEMA_VERSION,
        adapter_id=resolved_adapter_id,
        integration_mode=integration_mode,
        agent_kind=resolved_agent_kind,
        role=config.role,
        source_strategy_config=str(strategy_config_path),
        strategy_config_schema_version=config.schema_version,
        strategy_id=config.strategy_id,
        strategy_version=config.version,
        prompt_layers=config.prompt_layers,
        payload=_payload(config),
        integration_contract=_integration_contract(
            config=config,
            agent_kind=resolved_agent_kind,
            integration_mode=integration_mode,
            entrypoint_hint=entrypoint_hint,
        ),
        lineage=config.lineage,
        metadata={
            "base_prompt_fixed": True,
            "strategy_prompt_editable": True,
            "source_strategy_config_metadata": dict(config.metadata),
            **dict(metadata or {}),
        },
    )


def write_training_adapter_package(
    strategy_config_path: str | Path,
    output_path: str | Path,
    *,
    agent_kind: str,
    integration_mode: str = "prompt_config",
    adapter_id: str | None = None,
    entrypoint_hint: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> TrainingAdapterPackage:
    """Write an external training adapter package and return it."""

    package = generate_training_adapter_package(
        strategy_config_path,
        agent_kind=agent_kind,
        integration_mode=integration_mode,
        adapter_id=adapter_id,
        entrypoint_hint=entrypoint_hint,
        metadata=metadata,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, package)
    return package


def validate_training_adapter_package(
    path: str | Path,
) -> TrainingAdapterValidationResult:
    """Validate an external training adapter package without loading providers."""

    adapter_path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = read_json(adapter_path)
    except (OSError, ValueError) as exc:
        return TrainingAdapterValidationResult(
            schema_version=TRAINING_ADAPTER_VALIDATION_SCHEMA_VERSION,
            status="failed",
            path=str(adapter_path),
            errors=(str(exc),),
            warnings=(),
        )

    _validate_adapter_mapping(data, errors, warnings)
    return TrainingAdapterValidationResult(
        schema_version=TRAINING_ADAPTER_VALIDATION_SCHEMA_VERSION,
        status="passed" if not errors else "failed",
        path=str(adapter_path),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _payload(config: StrategyConfig) -> Mapping[str, Any]:
    return {
        "base_prompt": config.base_prompt,
        "strategy_prompt": config.strategy_prompt,
        "applied_lesson_ids": list(config.applied_lesson_ids),
        "applied_patches": list(config.applied_patches),
        "expected_improvements": list(config.expected_improvements),
        "source_candidate_id": config.source_candidate_id,
        "source_run_id": config.source_run_id,
        "source_battle_report": config.source_battle_report,
        "scenario_id": config.scenario_id,
        "opponent_profile_id": config.opponent_profile_id,
    }


def _integration_contract(
    *,
    config: StrategyConfig,
    agent_kind: str,
    integration_mode: str,
    entrypoint_hint: str | None,
) -> Mapping[str, Any]:
    contract: dict[str, Any] = {
        "code_mutation": False,
        "agent_kind": agent_kind,
        "role": config.role.value,
        "integration_mode": integration_mode,
        "load_order": ("base_prompt", "strategy_prompt"),
        "fixed_fields": ("base_prompt",),
        "editable_fields": ("strategy_prompt",),
        "expected_runtime_binding": {
            "role": config.role.value,
            "strategy_id": config.strategy_id,
            "strategy_version": config.version,
        },
        "consumer_requirements": (
            "Keep base_prompt read-only as the sandbox protocol layer.",
            "Load strategy_prompt as the editable policy layer for the user agent.",
            "Use this package only for agents running the recorded role.",
            "Record adapter_id and strategy_id in downstream evaluation metadata.",
        ),
        "out_of_scope": (
            "automatic source-code mutation",
            "remote plugin installation",
            "hosted deployment",
            "provider-specific SDK wiring",
        ),
    }
    if entrypoint_hint:
        contract["entrypoint_hint"] = entrypoint_hint
    return contract


def _validate_adapter_mapping(
    data: Mapping[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    _expect_equal(
        data,
        "schema_version",
        TRAINING_ADAPTER_SCHEMA_VERSION,
        errors,
    )
    _expect_non_empty(data, "adapter_id", errors)
    _expect_non_empty(data, "agent_kind", errors)
    _expect_non_empty(data, "source_strategy_config", errors)
    _expect_equal(
        data,
        "strategy_config_schema_version",
        STRATEGY_CONFIG_SCHEMA_VERSION,
        errors,
    )
    _expect_non_empty(data, "strategy_id", errors)
    version = data.get("strategy_version")
    if not isinstance(version, int) or version <= 0:
        errors.append("strategy_version: expected positive integer")
    try:
        Role(_expect_non_empty(data, "role", errors))
    except ValueError:
        errors.append("role: expected buyer or seller")

    mode = data.get("integration_mode")
    if mode not in SUPPORTED_INTEGRATION_MODES:
        errors.append(
            "integration_mode: expected one of "
            f"{sorted(SUPPORTED_INTEGRATION_MODES)!r}"
        )

    prompt_layers = data.get("prompt_layers")
    if not isinstance(prompt_layers, Mapping):
        errors.append("prompt_layers: expected object")
    else:
        try:
            if prompt_layers != prompt_layer_contract():
                raise StrategyConfigError("prompt_layers: contract mismatch")
        except StrategyConfigError as exc:
            errors.append(str(exc))

    payload = data.get("payload")
    if not isinstance(payload, Mapping):
        errors.append("payload: expected object")
    else:
        base_prompt = _expect_non_empty(payload, "base_prompt", errors)
        strategy_prompt = _expect_non_empty(payload, "strategy_prompt", errors)
        if base_prompt and base_prompt == strategy_prompt:
            errors.append("payload: base_prompt and strategy_prompt must differ")
        for key in ("applied_lesson_ids", "applied_patches", "expected_improvements"):
            _expect_string_list(payload, key, errors)

    contract = data.get("integration_contract")
    if not isinstance(contract, Mapping):
        errors.append("integration_contract: expected object")
    else:
        if contract.get("code_mutation") is not False:
            errors.append("integration_contract.code_mutation must be false")
        if contract.get("role") != data.get("role"):
            errors.append("integration_contract.role must match role")

    lineage = data.get("lineage")
    if not isinstance(lineage, list) or not lineage:
        errors.append("lineage: expected non-empty list")
    elif not all(isinstance(item, Mapping) for item in lineage):
        errors.append("lineage: every item must be an object")

    metadata = data.get("metadata")
    if not isinstance(metadata, Mapping):
        errors.append("metadata: expected object")
    else:
        if metadata.get("base_prompt_fixed") is not True:
            errors.append("metadata.base_prompt_fixed must be true")
        if metadata.get("strategy_prompt_editable") is not True:
            errors.append("metadata.strategy_prompt_editable must be true")
        if "source_strategy_config_metadata" not in metadata:
            warnings.append("metadata.source_strategy_config_metadata is missing")


def _expect_equal(
    data: Mapping[str, Any],
    key: str,
    expected: str,
    errors: list[str],
) -> None:
    if data.get(key) != expected:
        errors.append(f"{key}: expected {expected!r}, got {data.get(key)!r}")


def _expect_non_empty(
    data: Mapping[str, Any],
    key: str,
    errors: list[str],
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: expected non-empty string")
        return ""
    return value


def _expect_string_list(
    data: Mapping[str, Any],
    key: str,
    errors: list[str],
) -> None:
    value = data.get(key)
    if not isinstance(value, list):
        errors.append(f"{key}: expected list")
        return
    if not all(isinstance(item, str) for item in value):
        errors.append(f"{key}: every item must be a string")


def _non_empty(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingAdapterError(f"{key}: expected non-empty string")
    return value.strip()
