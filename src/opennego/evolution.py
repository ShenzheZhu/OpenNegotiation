"""Strategy evolution artifacts for policy-learning loops."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import read_json, write_json
from opennego.learning import POLICY_LEARNING_SCHEMA_VERSION
from opennego.schema import Role

STRATEGY_EVOLUTION_SCHEMA_VERSION = "opennego.strategy_evolution.v1"
STRATEGY_COMPARISON_SCHEMA_VERSION = "opennego.strategy_comparison.v1"


class StrategyEvolutionError(ValueError):
    """Raised when strategy evolution inputs are malformed."""


@dataclass(frozen=True)
class StrategyCandidate:
    schema_version: str
    candidate_id: str
    parent_strategy_id: str
    iteration: int
    user_role: Role
    source_battle_report: str
    source_run_id: str
    scenario_id: str
    opponent_profile_id: str | None
    strategy_prompt: str
    applied_lesson_ids: tuple[str, ...]
    applied_patches: tuple[str, ...]
    expected_improvements: tuple[str, ...]
    evaluation_plan: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyComparison:
    schema_version: str
    before_battle_report: str
    after_battle_report: str
    user_role: Role
    before_run_id: str
    after_run_id: str
    before_score: float
    after_score: float
    score_delta: float
    status: str
    before_outcome: str
    after_outcome: str
    deal_price_delta: float | None
    user_price_delta: float | None
    resolved_failure_modes: tuple[str, ...]
    new_failure_modes: tuple[str, ...]
    resolved_lesson_ids: tuple[str, ...]
    new_lesson_ids: tuple[str, ...]
    summary: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


def generate_strategy_candidate(
    battle_report_path: str | Path,
    *,
    parent_strategy_id: str = "user_strategy_v0",
    iteration: int = 1,
) -> StrategyCandidate:
    """Turn a battle report into a versioned strategy candidate."""

    if iteration <= 0:
        raise StrategyEvolutionError("iteration must be positive")
    report_path = Path(battle_report_path)
    report = _load_battle_report(report_path)
    user_role = Role(_required_str(report, "user_role"))
    candidate_id = f"{_slug(parent_strategy_id)}-iter-{iteration}"
    lessons = _lesson_items(report)
    patches = tuple(
        str(lesson["suggested_strategy_patch"])
        for lesson in lessons
        if lesson.get("suggested_strategy_patch")
    )
    lesson_ids = tuple(_required_str(lesson, "id") for lesson in lessons)
    expected_improvements = tuple(
        _expected_improvement(lesson)
        for lesson in lessons
        if lesson.get("recommendation")
    )
    opponent_profile_id = _optional_str(report, "opponent_profile_id")
    return StrategyCandidate(
        schema_version=STRATEGY_EVOLUTION_SCHEMA_VERSION,
        candidate_id=candidate_id,
        parent_strategy_id=parent_strategy_id,
        iteration=iteration,
        user_role=user_role,
        source_battle_report=str(report_path),
        source_run_id=_required_str(report, "run_id"),
        scenario_id=_required_str(report, "scenario_id"),
        opponent_profile_id=opponent_profile_id,
        strategy_prompt=_required_str(report, "suggested_strategy_prompt"),
        applied_lesson_ids=lesson_ids,
        applied_patches=patches,
        expected_improvements=expected_improvements,
        evaluation_plan=_evaluation_plan(
            candidate_id=candidate_id,
            user_role=user_role,
            opponent_profile_id=opponent_profile_id,
            source_battle_report=str(report_path),
        ),
        metadata={
            "base_prompt_fixed": True,
            "strategy_prompt_editable": True,
            "source_policy_score": _required_number(report, "score"),
            "source_failure_modes": tuple(_string_list(report, "failure_modes")),
        },
    )


def write_strategy_candidate(
    battle_report_path: str | Path,
    output_path: str | Path,
    *,
    parent_strategy_id: str = "user_strategy_v0",
    iteration: int = 1,
) -> Path:
    path = Path(output_path)
    candidate = generate_strategy_candidate(
        battle_report_path,
        parent_strategy_id=parent_strategy_id,
        iteration=iteration,
    )
    candidate = replace(
        candidate,
        evaluation_plan=_evaluation_plan(
            candidate_id=candidate.candidate_id,
            user_role=candidate.user_role,
            opponent_profile_id=candidate.opponent_profile_id,
            source_battle_report=candidate.source_battle_report,
            user_strategy_path=str(path),
        ),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, candidate)
    return path


def load_strategy_candidate(path: str | Path) -> StrategyCandidate:
    """Load and validate a versioned strategy candidate artifact."""

    candidate_path = Path(path)
    data = read_json(candidate_path)
    version = data.get("schema_version")
    if version != STRATEGY_EVOLUTION_SCHEMA_VERSION:
        raise StrategyEvolutionError(
            f"{candidate_path}: expected {STRATEGY_EVOLUTION_SCHEMA_VERSION}, "
            f"got {version!r}"
        )
    iteration = data.get("iteration")
    if not isinstance(iteration, int) or iteration <= 0:
        raise StrategyEvolutionError("iteration: expected positive integer")
    evaluation_plan = data.get("evaluation_plan", {})
    if not isinstance(evaluation_plan, Mapping):
        raise StrategyEvolutionError("evaluation_plan: expected object")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise StrategyEvolutionError("metadata: expected object")
    user_role = _required_role(data, "user_role")
    return StrategyCandidate(
        schema_version=STRATEGY_EVOLUTION_SCHEMA_VERSION,
        candidate_id=_required_str(data, "candidate_id"),
        parent_strategy_id=_required_str(data, "parent_strategy_id"),
        iteration=iteration,
        user_role=user_role,
        source_battle_report=_required_str(data, "source_battle_report"),
        source_run_id=_required_str(data, "source_run_id"),
        scenario_id=_required_str(data, "scenario_id"),
        opponent_profile_id=_optional_str(data, "opponent_profile_id"),
        strategy_prompt=_required_str(data, "strategy_prompt"),
        applied_lesson_ids=_string_list(data, "applied_lesson_ids"),
        applied_patches=_string_list(data, "applied_patches"),
        expected_improvements=_string_list(data, "expected_improvements"),
        evaluation_plan=evaluation_plan,
        metadata=metadata,
    )


def generate_strategy_comparison(
    before_battle_report_path: str | Path,
    after_battle_report_path: str | Path,
) -> StrategyComparison:
    """Compare two battle reports after a strategy rerun."""

    before_path = Path(before_battle_report_path)
    after_path = Path(after_battle_report_path)
    before = _load_battle_report(before_path)
    after = _load_battle_report(after_path)
    before_role = Role(_required_str(before, "user_role"))
    after_role = Role(_required_str(after, "user_role"))
    if before_role != after_role:
        raise StrategyEvolutionError(
            "cannot compare battle reports with different user_role values"
        )

    before_score = _required_number(before, "score")
    after_score = _required_number(after, "score")
    score_delta = round(after_score - before_score, 4)
    deal_price_delta = _deal_price_delta(before, after)
    user_price_delta = _user_price_delta(
        role=before_role,
        deal_price_delta=deal_price_delta,
    )
    before_failure_modes = set(_string_list(before, "failure_modes"))
    after_failure_modes = set(_string_list(after, "failure_modes"))
    before_lessons = set(_lesson_ids(before))
    after_lessons = set(_lesson_ids(after))
    status = _comparison_status(score_delta)
    return StrategyComparison(
        schema_version=STRATEGY_COMPARISON_SCHEMA_VERSION,
        before_battle_report=str(before_path),
        after_battle_report=str(after_path),
        user_role=before_role,
        before_run_id=_required_str(before, "run_id"),
        after_run_id=_required_str(after, "run_id"),
        before_score=before_score,
        after_score=after_score,
        score_delta=score_delta,
        status=status,
        before_outcome=_required_str(before, "outcome"),
        after_outcome=_required_str(after, "outcome"),
        deal_price_delta=deal_price_delta,
        user_price_delta=user_price_delta,
        resolved_failure_modes=tuple(sorted(before_failure_modes - after_failure_modes)),
        new_failure_modes=tuple(sorted(after_failure_modes - before_failure_modes)),
        resolved_lesson_ids=tuple(sorted(before_lessons - after_lessons)),
        new_lesson_ids=tuple(sorted(after_lessons - before_lessons)),
        summary=_comparison_summary(
            status=status,
            score_delta=score_delta,
            role=before_role,
            user_price_delta=user_price_delta,
        ),
        metadata={
            "before_opponent_profile_id": _optional_str(before, "opponent_profile_id"),
            "after_opponent_profile_id": _optional_str(after, "opponent_profile_id"),
            "before_scenario_id": _required_str(before, "scenario_id"),
            "after_scenario_id": _required_str(after, "scenario_id"),
        },
    )


def write_strategy_comparison(
    before_battle_report_path: str | Path,
    after_battle_report_path: str | Path,
    output_path: str | Path,
) -> Path:
    comparison = generate_strategy_comparison(
        before_battle_report_path,
        after_battle_report_path,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, comparison)
    return path


ACCEPTED_BATTLE_REPORT_VERSIONS = (
    POLICY_LEARNING_SCHEMA_VERSION,
    "opennego.battle_report.v2",
)


def _load_battle_report(path: Path) -> Mapping[str, Any]:
    report = read_json(path)
    version = report.get("schema_version")
    if version not in ACCEPTED_BATTLE_REPORT_VERSIONS:
        raise StrategyEvolutionError(
            f"{path}: expected one of {ACCEPTED_BATTLE_REPORT_VERSIONS}, "
            f"got {version!r}"
        )
    return report


def _evaluation_plan(
    *,
    candidate_id: str,
    user_role: Role,
    opponent_profile_id: str | None,
    source_battle_report: str,
    user_strategy_path: str = "<strategy_candidate.json>",
) -> Mapping[str, Any]:
    rerun_command = (
        f"opennego spar --user-role {user_role.value} "
        f"--output-dir runs/evolution/{candidate_id} "
        f"--user-strategy {user_strategy_path}"
    )
    if opponent_profile_id:
        rerun_command += f" --opponent-profile {opponent_profile_id}"
    compare_command = (
        f"opennego compare --before {source_battle_report} "
        f"--after runs/evolution/{candidate_id}/battle_report.json "
        f"--output runs/evolution/{candidate_id}/comparison.json"
    )
    return {
        "mode": "rerun_against_same_counterparty",
        "rerun_command": rerun_command,
        "compare_command": compare_command,
    }


def _lesson_items(report: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    lessons = report.get("lessons")
    if not isinstance(lessons, list):
        raise StrategyEvolutionError("lessons: expected list")
    parsed = tuple(lesson for lesson in lessons if isinstance(lesson, Mapping))
    if len(parsed) != len(lessons):
        raise StrategyEvolutionError("lessons: every item must be an object")
    return parsed


def _lesson_ids(report: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(_required_str(lesson, "id") for lesson in _lesson_items(report))


def _expected_improvement(lesson: Mapping[str, Any]) -> str:
    category = str(lesson.get("category", "strategy"))
    recommendation = _required_str(lesson, "recommendation")
    return f"{category}: {recommendation}"


def _deal_price_delta(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> float | None:
    before_price = before.get("deal_price")
    after_price = after.get("deal_price")
    if before_price is None or after_price is None:
        return None
    if not isinstance(before_price, (int, float)) or not isinstance(
        after_price,
        (int, float),
    ):
        raise StrategyEvolutionError("deal_price must be numeric or null")
    return round(float(after_price) - float(before_price), 4)


def _user_price_delta(
    *,
    role: Role,
    deal_price_delta: float | None,
) -> float | None:
    if deal_price_delta is None:
        return None
    if role == Role.BUYER:
        return round(-deal_price_delta, 4)
    if role == Role.SELLER:
        return deal_price_delta
    return None


def _comparison_status(score_delta: float) -> str:
    if score_delta > 0:
        return "improved"
    if score_delta < 0:
        return "regressed"
    return "unchanged"


def _comparison_summary(
    *,
    status: str,
    score_delta: float,
    role: Role,
    user_price_delta: float | None,
) -> str:
    price_part = ""
    if user_price_delta is not None:
        price_part = f" User-price delta for {role.value}: {user_price_delta:+.2f}."
    return f"Strategy {status}; policy score delta {score_delta:+.1f}.{price_part}"


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise StrategyEvolutionError(f"{key}: expected non-empty string")
    return value


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise StrategyEvolutionError(f"{key}: expected string or null")
    return value


def _required_number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)):
        raise StrategyEvolutionError(f"{key}: expected number")
    return float(value)


def _required_role(data: Mapping[str, Any], key: str) -> Role:
    value = _required_str(data, key)
    try:
        role = Role(value)
    except ValueError as exc:
        raise StrategyEvolutionError(f"{key}: expected buyer or seller") from exc
    if role not in (Role.BUYER, Role.SELLER):
        raise StrategyEvolutionError(f"{key}: expected buyer or seller")
    return role


def _string_list(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise StrategyEvolutionError(f"{key}: expected list")
    return tuple(str(item) for item in value)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    if not slug:
        raise StrategyEvolutionError("candidate_id: generated empty id")
    return slug
