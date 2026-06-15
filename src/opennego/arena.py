"""Reciprocal arena planning artifacts for benchmark methodology."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import read_json, write_json

ARENA_PLAN_SCHEMA_VERSION = "opennego.arena_plan.v1"


class ArenaPlanError(ValueError):
    """Raised when an arena plan request is malformed."""


@dataclass(frozen=True)
class ArenaMatchup:
    matchup_id: str
    scenario_id: str
    seed: int
    buyer_participant_id: str
    seller_participant_id: str
    reciprocal_group_id: str


@dataclass(frozen=True)
class ArenaPlan:
    schema_version: str
    status: str
    output_path: str | None
    participants: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    include_self_play: bool
    matchup_count: int
    reciprocal_group_count: int
    required_role_coverage: Mapping[str, tuple[str, ...]]
    ranking_methodology: Mapping[str, Any]
    matchups: tuple[ArenaMatchup, ...]
    warnings: tuple[str, ...]


def build_arena_plan(
    *,
    participants: Sequence[str],
    scenario_ids: Sequence[str] = ("real_market_demo",),
    seeds: Sequence[int] = (13,),
    include_self_play: bool = False,
    output_path: str | Path | None = None,
) -> ArenaPlan:
    """Build a reciprocal buyer/seller arena schedule without running it."""

    normalized_participants = _normalize_unique_strings(participants, "participant")
    normalized_scenarios = _normalize_unique_strings(scenario_ids, "scenario_id")
    normalized_seeds = _normalize_seeds(seeds)
    if len(normalized_participants) < 2:
        raise ArenaPlanError("participants: expected at least two unique ids")
    matchups = _matchups(
        participants=normalized_participants,
        scenario_ids=normalized_scenarios,
        seeds=normalized_seeds,
        include_self_play=include_self_play,
    )
    reciprocal_group_ids = {matchup.reciprocal_group_id for matchup in matchups}
    warnings = _warnings(
        participant_count=len(normalized_participants),
        include_self_play=include_self_play,
    )
    return ArenaPlan(
        schema_version=ARENA_PLAN_SCHEMA_VERSION,
        status="planned",
        output_path=str(output_path) if output_path is not None else None,
        participants=normalized_participants,
        scenario_ids=normalized_scenarios,
        seeds=normalized_seeds,
        include_self_play=include_self_play,
        matchup_count=len(matchups),
        reciprocal_group_count=len(reciprocal_group_ids),
        required_role_coverage={
            participant_id: ("buyer", "seller")
            for participant_id in normalized_participants
        },
        ranking_methodology={
            "primary": {
                "name": "deterministic_scorecard",
                "artifact": "opennego.leaderboard.v1",
                "status": "implemented",
                "summary": (
                    "Primary summaries use run metrics, transaction status, "
                    "market gap, tool behavior, and participant role coverage."
                ),
            },
            "arena_optional": {
                "name": "elo_or_bradley_terry",
                "status": "planned_optional_layer",
                "minimum_contract": (
                    "Use only after reciprocal participant-pair schedules exist "
                    "for shared scenarios and seeds."
                ),
                "not_in_current_plan": (
                    "This artifact schedules reciprocal matchups but does not "
                    "fit Elo or Bradley-Terry ratings."
                ),
            },
        },
        matchups=matchups,
        warnings=warnings,
    )


def write_arena_plan(
    output_path: str | Path,
    *,
    participants: Sequence[str],
    scenario_ids: Sequence[str] = ("real_market_demo",),
    seeds: Sequence[int] = (13,),
    include_self_play: bool = False,
) -> ArenaPlan:
    """Write a reciprocal arena plan artifact and return it."""

    output = Path(output_path)
    plan = build_arena_plan(
        participants=participants,
        scenario_ids=scenario_ids,
        seeds=seeds,
        include_self_play=include_self_play,
        output_path=output,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, plan)
    return plan


def load_arena_plan(path: str | Path) -> ArenaPlan:
    """Load a written arena plan artifact."""

    data = read_json(path)
    version = data.get("schema_version")
    if version != ARENA_PLAN_SCHEMA_VERSION:
        raise ArenaPlanError(
            f"{path}: expected {ARENA_PLAN_SCHEMA_VERSION}, got {version!r}"
        )
    raw_matchups = data.get("matchups")
    if not isinstance(raw_matchups, list):
        raise ArenaPlanError("matchups: expected list")
    matchups = tuple(_matchup_from_mapping(item) for item in raw_matchups)
    return ArenaPlan(
        schema_version=ARENA_PLAN_SCHEMA_VERSION,
        status=str(data.get("status", "planned")),
        output_path=data.get("output_path"),
        participants=tuple(str(p) for p in data.get("participants", ())),
        scenario_ids=tuple(str(s) for s in data.get("scenario_ids", ())),
        seeds=tuple(int(s) for s in data.get("seeds", ())),
        include_self_play=bool(data.get("include_self_play", False)),
        matchup_count=int(data.get("matchup_count", len(matchups))),
        reciprocal_group_count=int(data.get("reciprocal_group_count", 0)),
        required_role_coverage={
            str(pid): tuple(str(role) for role in roles)
            for pid, roles in (data.get("required_role_coverage") or {}).items()
        },
        ranking_methodology=data.get("ranking_methodology") or {},
        matchups=matchups,
        warnings=tuple(str(w) for w in data.get("warnings", ())),
    )


def _matchup_from_mapping(data: Mapping[str, Any]) -> ArenaMatchup:
    if not isinstance(data, Mapping):
        raise ArenaPlanError("matchups[]: expected object")
    return ArenaMatchup(
        matchup_id=str(data["matchup_id"]),
        scenario_id=str(data["scenario_id"]),
        seed=int(data["seed"]),
        buyer_participant_id=str(data["buyer_participant_id"]),
        seller_participant_id=str(data["seller_participant_id"]),
        reciprocal_group_id=str(data.get("reciprocal_group_id", "")),
    )


def _matchups(
    *,
    participants: tuple[str, ...],
    scenario_ids: tuple[str, ...],
    seeds: tuple[int, ...],
    include_self_play: bool,
) -> tuple[ArenaMatchup, ...]:
    matchups: list[ArenaMatchup] = []
    for scenario_id in scenario_ids:
        for seed in seeds:
            for buyer_index, buyer in enumerate(participants):
                for seller_index, seller in enumerate(participants):
                    if not include_self_play and buyer_index == seller_index:
                        continue
                    if buyer_index > seller_index:
                        continue
                    if buyer_index == seller_index:
                        group_id = _group_id(scenario_id, seed, buyer, seller)
                        matchups.append(
                            _matchup(
                                scenario_id=scenario_id,
                                seed=seed,
                                buyer=buyer,
                                seller=seller,
                                group_id=group_id,
                            )
                        )
                        continue
                    group_id = _group_id(scenario_id, seed, buyer, seller)
                    matchups.append(
                        _matchup(
                            scenario_id=scenario_id,
                            seed=seed,
                            buyer=buyer,
                            seller=seller,
                            group_id=group_id,
                        )
                    )
                    matchups.append(
                        _matchup(
                            scenario_id=scenario_id,
                            seed=seed,
                            buyer=seller,
                            seller=buyer,
                            group_id=group_id,
                        )
                    )
    return tuple(matchups)


def _matchup(
    *,
    scenario_id: str,
    seed: int,
    buyer: str,
    seller: str,
    group_id: str,
) -> ArenaMatchup:
    matchup_id = f"{_slug(scenario_id)}-seed-{seed}-{_slug(buyer)}-vs-{_slug(seller)}"
    return ArenaMatchup(
        matchup_id=matchup_id,
        scenario_id=scenario_id,
        seed=seed,
        buyer_participant_id=buyer,
        seller_participant_id=seller,
        reciprocal_group_id=group_id,
    )


def _group_id(scenario_id: str, seed: int, participant_a: str, participant_b: str) -> str:
    left, right = sorted((participant_a, participant_b))
    return f"{_slug(scenario_id)}-seed-{seed}-{_slug(left)}-{_slug(right)}"


def _normalize_unique_strings(values: Sequence[str], label: str) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ArenaPlanError(f"{label}: expected non-empty string")
        item = value.strip()
        if item in seen:
            raise ArenaPlanError(f"{label}: duplicate id {item!r}")
        seen.add(item)
        normalized.append(item)
    if not normalized:
        raise ArenaPlanError(f"{label}: expected at least one value")
    return tuple(normalized)


def _normalize_seeds(values: Sequence[int]) -> tuple[int, ...]:
    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        if not isinstance(value, int):
            raise ArenaPlanError("seed: expected integer")
        if value in seen:
            raise ArenaPlanError(f"seed: duplicate value {value}")
        seen.add(value)
        normalized.append(value)
    if not normalized:
        raise ArenaPlanError("seed: expected at least one value")
    return tuple(normalized)


def _warnings(
    *,
    participant_count: int,
    include_self_play: bool,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if participant_count < 3:
        warnings.append(
            "Two-participant plans are useful for smoke tests but too small for "
            "stable arena ratings."
        )
    if include_self_play:
        warnings.append("Self-play rows are diagnostic and should not drive rankings.")
    return tuple(warnings)


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
