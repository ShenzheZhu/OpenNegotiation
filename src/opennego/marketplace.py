"""Local strategy marketplace profile export utilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import read_json, write_json
from opennego.evolution import StrategyCandidate, load_strategy_candidate
from opennego.learning import (
    POLICY_LEARNING_SCHEMA_VERSION,
    StrategyProfile,
    load_strategy_registry,
)
from opennego.schema import Role
from opennego.strategy_config import (
    STRATEGY_CONFIG_SCHEMA_VERSION,
    base_prompt_for_role,
    prompt_layer_contract,
)

MARKETPLACE_PROFILE_SCHEMA_VERSION = "opennego.strategy_marketplace_profile.v1"
MARKETPLACE_VALIDATION_SCHEMA_VERSION = "opennego.strategy_marketplace_validation.v1"


class MarketplaceError(ValueError):
    """Raised when local marketplace artifacts are malformed."""


@dataclass(frozen=True)
class MarketplaceExportResult:
    profile_path: str
    profile_id: str
    installed_registry: str | None = None


@dataclass(frozen=True)
class MarketplaceValidationResult:
    schema_version: str
    status: str
    registry_file: str | None
    profile_files: tuple[str, ...]
    profile_count: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def generate_marketplace_profile(
    candidate_path: str | Path,
    *,
    profile_id: str | None = None,
    name: str | None = None,
    summary: str | None = None,
    difficulty: str = "custom",
    tags: Sequence[str] = (),
    allowed_tools: Sequence[str] | None = None,
) -> Mapping[str, Any]:
    """Convert a strategy candidate into a shareable local marketplace profile."""

    candidate = load_strategy_candidate(candidate_path)
    resolved_profile_id = profile_id or candidate.candidate_id
    _validate_profile_id(resolved_profile_id)
    role = candidate.user_role
    resolved_tools = (
        tuple(allowed_tools)
        if allowed_tools is not None
        else _default_tools(candidate)
    )
    profile = {
        "schema_version": MARKETPLACE_PROFILE_SCHEMA_VERSION,
        "id": resolved_profile_id,
        "name": name or _default_name(candidate),
        "role": role.value,
        "archetype": "shared_strategy",
        "difficulty": difficulty,
        "summary": summary or _default_summary(candidate),
        "base_prompt": _base_prompt(role),
        "strategy_prompt": candidate.strategy_prompt,
        "expected_traps": list(_expected_traps(candidate)),
        "allowed_tools": list(resolved_tools),
        "tags": list(_tags(candidate, tags)),
        "metadata": {
            "base_prompt_fixed": True,
            "strategy_prompt_editable": True,
            "strategy_config_version": STRATEGY_CONFIG_SCHEMA_VERSION,
            "marketplace_profile_schema_version": MARKETPLACE_PROFILE_SCHEMA_VERSION,
            "prompt_layers": _prompt_layers(),
            "source_type": "strategy_candidate",
            "source_schema_version": candidate.schema_version,
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
        },
    }
    StrategyProfile.from_mapping(profile)
    return profile


def write_marketplace_profile(
    candidate_path: str | Path,
    output_path: str | Path,
    *,
    profile_id: str | None = None,
    name: str | None = None,
    summary: str | None = None,
    difficulty: str = "custom",
    tags: Sequence[str] = (),
    allowed_tools: Sequence[str] | None = None,
    install_registry_path: str | Path | None = None,
    overwrite: bool = False,
) -> MarketplaceExportResult:
    """Write a marketplace profile and optionally install it into a registry."""

    profile = generate_marketplace_profile(
        candidate_path,
        profile_id=profile_id,
        name=name,
        summary=summary,
        difficulty=difficulty,
        tags=tags,
        allowed_tools=allowed_tools,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, profile)

    installed_registry = None
    if install_registry_path is not None:
        install_marketplace_profile(
            profile,
            install_registry_path,
            overwrite=overwrite,
        )
        installed_registry = str(install_registry_path)

    return MarketplaceExportResult(
        profile_path=str(output),
        profile_id=str(profile["id"]),
        installed_registry=installed_registry,
    )


def load_marketplace_profile(path: str | Path) -> StrategyProfile:
    """Load a marketplace profile artifact as a StrategyProfile."""

    data = read_json(path)
    version = data.get("schema_version")
    if version != MARKETPLACE_PROFILE_SCHEMA_VERSION:
        raise MarketplaceError(
            f"{path}: expected {MARKETPLACE_PROFILE_SCHEMA_VERSION}, got {version!r}"
        )
    return StrategyProfile.from_mapping(data)


def validate_marketplace_configs(
    *,
    registry_path: str | Path | None = None,
    profile_paths: Sequence[str | Path] = (),
) -> MarketplaceValidationResult:
    """Validate local strategy marketplace registries and profile artifacts."""

    errors: list[str] = []
    warnings: list[str] = []
    profile_count = 0
    if registry_path is not None:
        profile_count += _validate_registry_file(
            Path(registry_path),
            errors=errors,
            warnings=warnings,
        )
    for profile_path in profile_paths:
        profile_count += _validate_standalone_profile_file(
            Path(profile_path),
            errors=errors,
            warnings=warnings,
        )
    if registry_path is None and not profile_paths:
        errors.append("marketplace: provide a registry or at least one profile file")

    return MarketplaceValidationResult(
        schema_version=MARKETPLACE_VALIDATION_SCHEMA_VERSION,
        status="passed" if not errors else "failed",
        registry_file=str(registry_path) if registry_path is not None else None,
        profile_files=tuple(str(path) for path in profile_paths),
        profile_count=profile_count,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def install_marketplace_profile(
    profile: Mapping[str, Any] | StrategyProfile,
    registry_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Install a marketplace profile into a local StrategyRegistry JSON file."""

    profile_payload = _profile_payload(profile)
    StrategyProfile.from_mapping(profile_payload)
    registry_file = Path(registry_path)
    registry = _registry_payload(registry_file)
    profiles = list(registry["profiles"])
    profile_id = profile_payload["id"]
    existing_index = next(
        (index for index, item in enumerate(profiles) if item.get("id") == profile_id),
        None,
    )
    if existing_index is not None and not overwrite:
        raise MarketplaceError(
            f"{registry_file}: profile id {profile_id!r} already exists"
        )
    if existing_index is None:
        profiles.append(profile_payload)
    else:
        profiles[existing_index] = profile_payload

    registry_file.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        registry_file,
        {
            "schema_version": POLICY_LEARNING_SCHEMA_VERSION,
            "profiles": profiles,
        },
    )
    load_strategy_registry(registry_file)
    return registry_file


def _profile_payload(profile: Mapping[str, Any] | StrategyProfile) -> Mapping[str, Any]:
    if isinstance(profile, StrategyProfile):
        payload: dict[str, Any] = {
            "id": profile.id,
            "name": profile.name,
            "role": profile.role.value,
            "archetype": profile.archetype,
            "difficulty": profile.difficulty,
            "summary": profile.summary,
            "base_prompt": profile.base_prompt,
            "strategy_prompt": profile.strategy_prompt,
            "expected_traps": list(profile.expected_traps),
            "allowed_tools": list(profile.allowed_tools),
            "tags": list(profile.tags),
            "metadata": dict(profile.metadata),
        }
        profile_schema = profile.metadata.get("marketplace_profile_schema_version")
        if profile_schema:
            payload["schema_version"] = profile_schema
        return payload
    return dict(profile)


def _registry_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": POLICY_LEARNING_SCHEMA_VERSION, "profiles": []}
    data = json.loads(path.read_text())
    if not isinstance(data, Mapping):
        raise MarketplaceError(f"{path}: expected registry object")
    version = data.get("schema_version")
    if version != POLICY_LEARNING_SCHEMA_VERSION:
        raise MarketplaceError(
            f"{path}: expected {POLICY_LEARNING_SCHEMA_VERSION}, got {version!r}"
        )
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        raise MarketplaceError(f"{path}: profiles must be a list")
    return {"schema_version": POLICY_LEARNING_SCHEMA_VERSION, "profiles": profiles}


def _default_name(candidate: StrategyCandidate) -> str:
    return f"Shared {candidate.user_role.value.title()} Strategy: {candidate.candidate_id}"


def _default_summary(candidate: StrategyCandidate) -> str:
    if candidate.expected_improvements:
        return candidate.expected_improvements[0]
    if candidate.applied_lesson_ids:
        lessons = ", ".join(candidate.applied_lesson_ids[:3])
        return f"Shared strategy candidate derived from lessons: {lessons}."
    return "Shared strategy candidate derived from an OpenNegotiation training run."


def _base_prompt(role: Role) -> str:
    return base_prompt_for_role(role)


def _prompt_layers() -> Mapping[str, Mapping[str, object]]:
    return prompt_layer_contract()


def _validate_registry_file(
    path: Path,
    *,
    errors: list[str],
    warnings: list[str],
) -> int:
    registry = _load_json_object(path, "registry", errors)
    if not registry:
        return 0
    version = registry.get("schema_version")
    if version != POLICY_LEARNING_SCHEMA_VERSION:
        errors.append(
            f"{path}: schema_version expected {POLICY_LEARNING_SCHEMA_VERSION!r}, "
            f"got {version!r}"
        )
    profiles = registry.get("profiles")
    if not isinstance(profiles, list):
        errors.append(f"{path}: profiles must be a list")
        return 0
    seen: set[str] = set()
    for index, profile in enumerate(profiles):
        label = f"{path}:profiles[{index}]"
        if not isinstance(profile, Mapping):
            errors.append(f"{label}: expected object")
            continue
        profile_id = str(profile.get("id", ""))
        if profile_id in seen:
            errors.append(f"{label}.id: duplicate profile id {profile_id!r}")
        seen.add(profile_id)
        _validate_profile_contract(
            profile,
            label=label,
            require_profile_schema=False,
            errors=errors,
            warnings=warnings,
        )
    try:
        load_strategy_registry(path)
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f"{path}: cannot load as StrategyRegistry: {exc}")
    return len(profiles)


def _validate_standalone_profile_file(
    path: Path,
    *,
    errors: list[str],
    warnings: list[str],
) -> int:
    profile = _load_json_object(path, "profile", errors)
    if not profile:
        return 0
    _validate_profile_contract(
        profile,
        label=str(path),
        require_profile_schema=True,
        errors=errors,
        warnings=warnings,
    )
    try:
        load_marketplace_profile(path)
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f"{path}: cannot load as marketplace profile: {exc}")
    return 1


def _validate_profile_contract(
    profile: Mapping[str, Any],
    *,
    label: str,
    require_profile_schema: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    profile_schema = profile.get("schema_version")
    if require_profile_schema and profile_schema != MARKETPLACE_PROFILE_SCHEMA_VERSION:
        errors.append(
            f"{label}.schema_version: expected {MARKETPLACE_PROFILE_SCHEMA_VERSION!r}, "
            f"got {profile_schema!r}"
        )
    if profile_schema is not None and profile_schema != MARKETPLACE_PROFILE_SCHEMA_VERSION:
        errors.append(
            f"{label}.schema_version: expected {MARKETPLACE_PROFILE_SCHEMA_VERSION!r}, "
            f"got {profile_schema!r}"
        )

    profile_id = profile.get("id")
    if not isinstance(profile_id, str):
        errors.append(f"{label}.id: expected non-empty string")
    else:
        try:
            _validate_profile_id(profile_id)
        except MarketplaceError as exc:
            errors.append(f"{label}.id: {exc}")

    base_prompt = profile.get("base_prompt")
    strategy_prompt = profile.get("strategy_prompt")
    if not isinstance(base_prompt, str) or not base_prompt.strip():
        errors.append(f"{label}.base_prompt: expected non-empty string")
    if not isinstance(strategy_prompt, str) or not strategy_prompt.strip():
        errors.append(f"{label}.strategy_prompt: expected non-empty string")
    if isinstance(base_prompt, str) and base_prompt == strategy_prompt:
        errors.append(f"{label}: base_prompt and strategy_prompt must be distinct")

    metadata = profile.get("metadata")
    if not isinstance(metadata, Mapping):
        errors.append(f"{label}.metadata: expected object")
        metadata = {}
    if metadata.get("base_prompt_fixed") is not True:
        errors.append(f"{label}.metadata.base_prompt_fixed must be true")
    if metadata.get("strategy_prompt_editable") is not True:
        errors.append(f"{label}.metadata.strategy_prompt_editable must be true")
    strategy_version = metadata.get("strategy_config_version")
    if strategy_version != STRATEGY_CONFIG_SCHEMA_VERSION:
        errors.append(
            f"{label}.metadata.strategy_config_version: expected "
            f"{STRATEGY_CONFIG_SCHEMA_VERSION!r}, got {strategy_version!r}"
        )
    _validate_prompt_layers(metadata, label=label, errors=errors)
    if (
        metadata.get("source_type") == "strategy_candidate"
        and profile_schema != MARKETPLACE_PROFILE_SCHEMA_VERSION
    ):
        errors.append(
            f"{label}: shared strategy_candidate profiles must carry "
            f"{MARKETPLACE_PROFILE_SCHEMA_VERSION}"
        )

    try:
        StrategyProfile.from_mapping(profile)
    except (ValueError, KeyError) as exc:
        errors.append(f"{label}: cannot parse as StrategyProfile: {exc}")
    if not profile_schema and metadata.get("source_type") not in {None, "curated_npc"}:
        warnings.append(f"{label}.schema_version: absent for registry profile")


def _validate_prompt_layers(
    metadata: Mapping[str, Any],
    *,
    label: str,
    errors: list[str],
) -> None:
    layers = metadata.get("prompt_layers")
    if not isinstance(layers, Mapping):
        errors.append(f"{label}.metadata.prompt_layers: expected object")
        return
    expected = _prompt_layers()
    for layer_name, contract in expected.items():
        layer = layers.get(layer_name)
        if not isinstance(layer, Mapping):
            errors.append(f"{label}.metadata.prompt_layers.{layer_name}: expected object")
            continue
        for key, expected_value in contract.items():
            if layer.get(key) != expected_value:
                errors.append(
                    f"{label}.metadata.prompt_layers.{layer_name}.{key}: expected "
                    f"{expected_value!r}, got {layer.get(key)!r}"
                )


def _load_json_object(
    path: Path,
    label: str,
    errors: list[str],
) -> Mapping[str, Any]:
    try:
        data = read_json(path)
    except (OSError, ValueError) as exc:
        errors.append(f"{path}: cannot read {label} JSON object: {exc}")
        return {}
    if not isinstance(data, Mapping):
        errors.append(f"{path}: expected {label} JSON object")
        return {}
    return data


def _expected_traps(candidate: StrategyCandidate) -> tuple[str, ...]:
    if candidate.expected_improvements:
        return tuple(
            f"Trace-grounded improvement target: {item}"
            for item in candidate.expected_improvements
        )
    return tuple(
        f"Derived from policy lesson: {lesson_id}"
        for lesson_id in candidate.applied_lesson_ids
    )


def _default_tools(candidate: StrategyCandidate) -> tuple[str, ...]:
    if "missed_market_tool" in candidate.applied_lesson_ids:
        return ("market_price_search",)
    return ()


def _tags(candidate: StrategyCandidate, extra: Sequence[str]) -> tuple[str, ...]:
    tags = [
        "shared",
        "strategy-candidate",
        candidate.user_role.value,
        _slug(candidate.parent_strategy_id),
    ]
    tags.extend(_slug(item) for item in candidate.applied_lesson_ids)
    tags.extend(_slug(item) for item in extra)
    return tuple(dict.fromkeys(tag for tag in tags if tag))


def _validate_profile_id(profile_id: str) -> None:
    if not isinstance(profile_id, str) or not profile_id:
        raise MarketplaceError("profile_id: expected non-empty string")
    if profile_id != _slug(profile_id):
        raise MarketplaceError(
            "profile_id: use only letters, numbers, underscores, dots, and hyphens"
        )


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    if not slug:
        raise MarketplaceError("slug: generated empty value")
    return slug
