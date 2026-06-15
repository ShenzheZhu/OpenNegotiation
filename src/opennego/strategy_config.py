"""Versioned strategy configuration artifacts for user-agent evolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from opennego.artifacts import read_json, write_json
from opennego.evolution import StrategyCandidate, load_strategy_candidate
from opennego.schema import Role

STRATEGY_CONFIG_SCHEMA_VERSION = "opennego.strategy_config.v1"


class StrategyConfigError(ValueError):
    """Raised when a strategy config artifact is malformed."""


@dataclass(frozen=True)
class StrategyConfig:
    schema_version: str
    strategy_id: str
    version: int
    role: Role
    base_prompt: str
    strategy_prompt: str
    prompt_layers: Mapping[str, Mapping[str, object]]
    source_candidate_id: str
    parent_strategy_id: str
    source_battle_report: str
    source_run_id: str
    scenario_id: str
    opponent_profile_id: str | None
    applied_lesson_ids: tuple[str, ...]
    applied_patches: tuple[str, ...]
    expected_improvements: tuple[str, ...]
    lineage: tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


def prompt_layer_contract() -> Mapping[str, Mapping[str, object]]:
    """Return the fixed-base/editable-strategy prompt-layer contract."""

    return {
        "base_prompt": {
            "field": "base_prompt",
            "editable": False,
            "scope": "sandbox_protocol",
        },
        "strategy_prompt": {
            "field": "strategy_prompt",
            "editable": True,
            "scope": "strategy_policy",
        },
    }


def base_prompt_for_role(role: Role) -> str:
    """Return the fixed sandbox prompt used by shared strategy configs."""

    return (
        f"Follow OpenNegotiation {role.value} protocol exactly: return one valid action, "
        "respect role constraints, never alter tool permissions, and keep the "
        "base sandbox rules fixed."
    )


def generate_strategy_config(
    candidate_path: str | Path,
    *,
    base_config_path: str | Path | None = None,
    strategy_id: str | None = None,
    allow_train_only: bool = False,
) -> StrategyConfig:
    """Apply a strategy candidate into a versioned strategy config artifact."""

    candidate = load_strategy_candidate(candidate_path)
    verdict = candidate.metadata.get("generalization_verdict")
    if verdict == "train_only" and not allow_train_only:
        raise StrategyConfigError(
            "candidate failed held-out generalization (verdict=train_only): it "
            "improved only against the profiles it trained on. Re-run training "
            "or pass allow_train_only to apply it anyway."
        )
    base_config = (
        load_strategy_config(base_config_path) if base_config_path is not None else None
    )
    if base_config is not None and base_config.role != candidate.user_role:
        raise StrategyConfigError(
            "base_config.role must match strategy candidate user_role"
        )
    resolved_strategy_id = strategy_id or candidate.candidate_id
    _require_non_empty_string(resolved_strategy_id, "strategy_id")
    resolved_base_prompt = (
        base_config.base_prompt
        if base_config is not None
        else base_prompt_for_role(candidate.user_role)
    )
    if candidate.strategy_prompt.strip() == resolved_base_prompt.strip():
        raise StrategyConfigError(
            "candidate strategy_prompt must not overwrite the fixed base "
            "prompt: strategy evolution may only edit the strategy layer"
        )
    version = _next_version(candidate, base_config)
    lineage_entry = _lineage_entry(candidate, candidate_path)
    lineage = (
        tuple(base_config.lineage) + (lineage_entry,)
        if base_config is not None
        else (lineage_entry,)
    )
    metadata = _metadata(
        candidate=candidate,
        candidate_path=candidate_path,
        base_config=base_config,
        base_config_path=base_config_path,
    )
    return StrategyConfig(
        schema_version=STRATEGY_CONFIG_SCHEMA_VERSION,
        strategy_id=resolved_strategy_id,
        version=version,
        role=candidate.user_role,
        base_prompt=resolved_base_prompt,
        strategy_prompt=candidate.strategy_prompt,
        prompt_layers=prompt_layer_contract(),
        source_candidate_id=candidate.candidate_id,
        parent_strategy_id=candidate.parent_strategy_id,
        source_battle_report=candidate.source_battle_report,
        source_run_id=candidate.source_run_id,
        scenario_id=candidate.scenario_id,
        opponent_profile_id=candidate.opponent_profile_id,
        applied_lesson_ids=candidate.applied_lesson_ids,
        applied_patches=candidate.applied_patches,
        expected_improvements=candidate.expected_improvements,
        lineage=lineage,
        metadata=metadata,
    )


def write_strategy_config(
    candidate_path: str | Path,
    output_path: str | Path,
    *,
    base_config_path: str | Path | None = None,
    strategy_id: str | None = None,
    allow_train_only: bool = False,
) -> Path:
    """Write an applied strategy config and return its path."""

    config = generate_strategy_config(
        candidate_path,
        base_config_path=base_config_path,
        strategy_id=strategy_id,
        allow_train_only=allow_train_only,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, config)
    return output


def load_strategy_config(path: str | Path) -> StrategyConfig:
    """Load and validate a versioned strategy config artifact."""

    config_path = Path(path)
    data = read_json(config_path)
    version = data.get("schema_version")
    if version != STRATEGY_CONFIG_SCHEMA_VERSION:
        raise StrategyConfigError(
            f"{config_path}: expected {STRATEGY_CONFIG_SCHEMA_VERSION}, "
            f"got {version!r}"
        )
    role = _required_role(data, "role")
    config_version = data.get("version")
    if not isinstance(config_version, int) or config_version <= 0:
        raise StrategyConfigError("version: expected positive integer")
    strategy_id = _required_str(data, "strategy_id")
    base_prompt = _required_str(data, "base_prompt")
    strategy_prompt = _required_str(data, "strategy_prompt")
    if base_prompt == strategy_prompt:
        raise StrategyConfigError("base_prompt and strategy_prompt must be distinct")
    prompt_layers = _required_mapping(data, "prompt_layers")
    _validate_prompt_layers(prompt_layers)
    metadata = _optional_mapping(data, "metadata")
    _validate_metadata(metadata)
    lineage = _mapping_sequence(data, "lineage")
    if not lineage:
        raise StrategyConfigError("lineage: expected at least one entry")
    return StrategyConfig(
        schema_version=STRATEGY_CONFIG_SCHEMA_VERSION,
        strategy_id=strategy_id,
        version=config_version,
        role=role,
        base_prompt=base_prompt,
        strategy_prompt=strategy_prompt,
        prompt_layers=prompt_layers,
        source_candidate_id=_required_str(data, "source_candidate_id"),
        parent_strategy_id=_required_str(data, "parent_strategy_id"),
        source_battle_report=_required_str(data, "source_battle_report"),
        source_run_id=_required_str(data, "source_run_id"),
        scenario_id=_required_str(data, "scenario_id"),
        opponent_profile_id=_optional_str(data, "opponent_profile_id"),
        applied_lesson_ids=_string_tuple(data, "applied_lesson_ids"),
        applied_patches=_string_tuple(data, "applied_patches"),
        expected_improvements=_string_tuple(data, "expected_improvements"),
        lineage=lineage,
        metadata=metadata,
    )


def _next_version(
    candidate: StrategyCandidate,
    base_config: StrategyConfig | None,
) -> int:
    if base_config is not None:
        return base_config.version + 1
    return candidate.iteration


def _metadata(
    *,
    candidate: StrategyCandidate,
    candidate_path: str | Path,
    base_config: StrategyConfig | None,
    base_config_path: str | Path | None,
) -> Mapping[str, Any]:
    metadata: dict[str, Any] = {
        "base_prompt_fixed": True,
        "strategy_prompt_editable": True,
        "strategy_config_version": STRATEGY_CONFIG_SCHEMA_VERSION,
        "prompt_layers": prompt_layer_contract(),
        "source_type": "strategy_candidate",
        "source_schema_version": candidate.schema_version,
        "candidate_path": str(candidate_path),
        "candidate_id": candidate.candidate_id,
        "parent_strategy_id": candidate.parent_strategy_id,
        "iteration": candidate.iteration,
        "source_battle_report": candidate.source_battle_report,
        "source_run_id": candidate.source_run_id,
        "scenario_id": candidate.scenario_id,
        "opponent_profile_id": candidate.opponent_profile_id,
        "applied_lesson_ids": list(candidate.applied_lesson_ids),
        "applied_patches": list(candidate.applied_patches),
        "expected_improvements": list(candidate.expected_improvements),
    }
    if base_config is not None:
        metadata["previous_strategy_id"] = base_config.strategy_id
        metadata["previous_strategy_version"] = base_config.version
        metadata["base_config_path"] = str(base_config_path)
    return metadata


def _lineage_entry(
    candidate: StrategyCandidate,
    candidate_path: str | Path,
) -> Mapping[str, Any]:
    return {
        "source_type": "strategy_candidate",
        "candidate_path": str(candidate_path),
        "candidate_id": candidate.candidate_id,
        "parent_strategy_id": candidate.parent_strategy_id,
        "candidate_iteration": candidate.iteration,
        "source_battle_report": candidate.source_battle_report,
        "source_run_id": candidate.source_run_id,
        "applied_lesson_ids": list(candidate.applied_lesson_ids),
        "applied_patches": list(candidate.applied_patches),
    }


def _validate_prompt_layers(layers: Mapping[str, Any]) -> None:
    expected = prompt_layer_contract()
    for name, contract in expected.items():
        layer = layers.get(name)
        if not isinstance(layer, Mapping):
            raise StrategyConfigError(f"prompt_layers.{name}: expected object")
        for key, expected_value in contract.items():
            if layer.get(key) != expected_value:
                raise StrategyConfigError(
                    f"prompt_layers.{name}.{key}: expected "
                    f"{expected_value!r}, got {layer.get(key)!r}"
                )


def _validate_metadata(metadata: Mapping[str, Any]) -> None:
    if metadata.get("base_prompt_fixed") is not True:
        raise StrategyConfigError("metadata.base_prompt_fixed must be true")
    if metadata.get("strategy_prompt_editable") is not True:
        raise StrategyConfigError("metadata.strategy_prompt_editable must be true")
    if metadata.get("strategy_config_version") != STRATEGY_CONFIG_SCHEMA_VERSION:
        raise StrategyConfigError(
            "metadata.strategy_config_version: expected "
            f"{STRATEGY_CONFIG_SCHEMA_VERSION!r}"
        )
    layers = metadata.get("prompt_layers")
    if not isinstance(layers, Mapping):
        raise StrategyConfigError("metadata.prompt_layers: expected object")
    _validate_prompt_layers(layers)


def _required_role(data: Mapping[str, Any], key: str) -> Role:
    try:
        return Role(_required_str(data, key))
    except ValueError as exc:
        raise StrategyConfigError(f"{key}: expected buyer or seller") from exc


def _required_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise StrategyConfigError(f"{key}: expected object")
    return value


def _optional_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise StrategyConfigError(f"{key}: expected object")
    return value


def _mapping_sequence(data: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    value = data.get(key)
    if not isinstance(value, list):
        raise StrategyConfigError(f"{key}: expected list")
    parsed = tuple(item for item in value if isinstance(item, Mapping))
    if len(parsed) != len(value):
        raise StrategyConfigError(f"{key}: every item must be an object")
    return parsed


def _string_tuple(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, ())
    if not isinstance(value, list):
        raise StrategyConfigError(f"{key}: expected list")
    parsed = tuple(str(item) for item in value if isinstance(item, str))
    if len(parsed) != len(value):
        raise StrategyConfigError(f"{key}: every item must be a string")
    return parsed


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise StrategyConfigError(f"{key}: expected string or null")
    return value


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    return _require_non_empty_string(value, key)


def _require_non_empty_string(value: object, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategyConfigError(f"{key}: expected non-empty string")
    return value
