"""Policy-learning reports and NPC strategy registry utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from opennego.artifacts import write_json
from opennego.schema import ActionType, Role

if TYPE_CHECKING:
    from opennego.ports.coach import CoachPort

POLICY_LEARNING_SCHEMA_VERSION = "opennego.policy_learning.v1"
DEFAULT_NPC_REGISTRY_PATH = Path("examples/data/npc_strategies.json")


@dataclass(frozen=True)
class StrategyProfile:
    """A preset NPC or strategy module that users can spar against."""

    id: str
    name: str
    role: Role
    archetype: str
    difficulty: str
    summary: str
    base_prompt: str
    strategy_prompt: str
    expected_traps: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "StrategyProfile":
        return cls(
            id=_required_str(data, "id"),
            name=_required_str(data, "name"),
            role=Role(_required_str(data, "role")),
            archetype=_required_str(data, "archetype"),
            difficulty=_required_str(data, "difficulty"),
            summary=str(data.get("summary", "")),
            base_prompt=_required_str(data, "base_prompt"),
            strategy_prompt=_required_str(data, "strategy_prompt"),
            expected_traps=tuple(str(item) for item in data.get("expected_traps", ())),
            allowed_tools=tuple(str(item) for item in data.get("allowed_tools", ())),
            tags=tuple(str(item) for item in data.get("tags", ())),
            metadata=_optional_mapping(data, "metadata"),
        )


@dataclass(frozen=True)
class StrategyRegistry:
    schema_version: str
    profiles: tuple[StrategyProfile, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "StrategyRegistry":
        version = data.get("schema_version")
        if version != POLICY_LEARNING_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version: expected {POLICY_LEARNING_SCHEMA_VERSION!r}, got {version!r}"
            )
        profiles = data.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            raise ValueError("profiles: expected non-empty list")
        parsed = tuple(
            StrategyProfile.from_mapping(profile)
            for profile in profiles
            if isinstance(profile, Mapping)
        )
        if len(parsed) != len(profiles):
            raise ValueError("profiles: every item must be an object")
        ids = [profile.id for profile in parsed]
        if len(ids) != len(set(ids)):
            raise ValueError("profiles: ids must be unique")
        return cls(schema_version=POLICY_LEARNING_SCHEMA_VERSION, profiles=parsed)

    @classmethod
    def from_json(cls, path: str | Path) -> "StrategyRegistry":
        data = json.loads(Path(path).read_text())
        if not isinstance(data, Mapping):
            raise ValueError(f"{path}: expected JSON object")
        return cls.from_mapping(data)

    def by_id(self, profile_id: str) -> StrategyProfile:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        raise KeyError(f"Unknown strategy profile: {profile_id}")

    def for_role(self, role: Role | str) -> tuple[StrategyProfile, ...]:
        normalized = Role(role)
        return tuple(profile for profile in self.profiles if profile.role == normalized)


@dataclass(frozen=True)
class EvidenceRef:
    event_index: int
    turn: int
    role: Role
    action_type: ActionType
    summary: str


@dataclass(frozen=True)
class PolicyLesson:
    id: str
    severity: str
    category: str
    finding: str
    recommendation: str
    evidence: tuple[EvidenceRef, ...] = ()
    suggested_strategy_patch: str | None = None


def load_strategy_registry(path: str | Path = DEFAULT_NPC_REGISTRY_PATH) -> StrategyRegistry:
    return StrategyRegistry.from_json(path)


def generate_battle_report(
    run_dir: str | Path,
    *,
    user_role: Role | str = Role.BUYER,
    npc_registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    opponent_profile_id: str | None = None,
    coach: "CoachPort | None" = None,
):
    """Review one run through a coach and return a v2 battle report."""

    from opennego.coaching import review_run

    return review_run(
        run_dir,
        user_role=user_role,
        coach=coach,
        registry_path=npc_registry_path,
        opponent_profile_id=opponent_profile_id,
    )


def write_battle_report(
    run_dir: str | Path,
    output_path: str | Path,
    *,
    user_role: Role | str = Role.BUYER,
    npc_registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    opponent_profile_id: str | None = None,
    coach: "CoachPort | None" = None,
) -> Path:
    report = generate_battle_report(
        run_dir,
        user_role=user_role,
        npc_registry_path=npc_registry_path,
        opponent_profile_id=opponent_profile_id,
        coach=coach,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, report)
    return path


def registry_listing(
    registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    *,
    role: Role | str | None = None,
) -> Mapping[str, Any]:
    registry = load_strategy_registry(registry_path)
    profiles = registry.profiles if role is None else registry.for_role(Role(role))
    return {
        "schema_version": registry.schema_version,
        "profiles": [
            {
                "id": profile.id,
                "name": profile.name,
                "role": profile.role.value,
                "archetype": profile.archetype,
                "difficulty": profile.difficulty,
                "summary": profile.summary,
                "expected_traps": list(profile.expected_traps),
                "allowed_tools": list(profile.allowed_tools),
                "tags": list(profile.tags),
            }
            for profile in profiles
        ],
    }


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key}: expected non-empty string")
    return value


def _optional_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{key}: expected object")
    return value
