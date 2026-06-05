"""No-key strategy sparring suite orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from opennego.artifacts import write_json
from opennego.learning import (
    DEFAULT_NPC_REGISTRY_PATH,
    BattleReport,
    StrategyProfile,
    generate_battle_report,
    load_strategy_registry,
)
from opennego.runner import (
    ConfigValidationError,
    ExperimentSummary,
    RunRecord,
    run_experiment_config,
)
from opennego.schema import Role

SPARRING_SUITE_SCHEMA_VERSION = "opennego.sparring_suite.v1"
SPARRING_EXECUTION_MODE = "fixture_profile_diagnosis"


@dataclass(frozen=True)
class SparringOpponentResult:
    profile_id: str
    profile_name: str
    profile_role: Role
    difficulty: str
    status: str
    benchmark_output_dir: str
    benchmark_completed: int
    benchmark_failed: int
    learning_input_dir: str | None = None
    battle_report: str | None = None
    outcome: str | None = None
    deal_price: float | None = None
    policy_score: float | None = None
    failure_modes: tuple[str, ...] = ()
    lesson_ids: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class SparringSuiteSummary:
    schema_version: str
    name: str
    execution_mode: str
    output_dir: str
    config_path: str
    registry_path: str
    user_role: Role
    opponent_role: Role
    total_profiles: int
    completed: int
    failed: int
    results: tuple[SparringOpponentResult, ...]
    artifact_path: str


def run_sparring_suite(
    *,
    output_dir: str | Path = "runs/sparring_suite",
    config_path: str | Path = "configs/real_market_demo.yaml",
    registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    user_role: Role | str = Role.BUYER,
    opponent_profile_ids: Sequence[str] | None = None,
    learning_tool_regime: str = "no_tools",
    fail_fast: bool = True,
) -> SparringSuiteSummary:
    """Run deterministic sparring diagnostics for selected strategy profiles."""

    output = Path(output_dir)
    registry = load_strategy_registry(registry_path)
    normalized_user_role = Role(user_role)
    opponent_role = _opponent_role(normalized_user_role)
    profiles = _select_profiles(
        registry.profiles,
        opponent_role=opponent_role,
        requested_ids=opponent_profile_ids,
    )

    results: list[SparringOpponentResult] = []
    for profile in profiles:
        try:
            results.append(
                _run_profile_sparring(
                    profile=profile,
                    output_dir=output / "profiles" / profile.id,
                    config_path=config_path,
                    registry_path=registry_path,
                    user_role=normalized_user_role,
                    learning_tool_regime=learning_tool_regime,
                )
            )
        except (OSError, ValueError, KeyError, ConfigValidationError) as exc:
            result = SparringOpponentResult(
                profile_id=profile.id,
                profile_name=profile.name,
                profile_role=profile.role,
                difficulty=profile.difficulty,
                status="failed",
                benchmark_output_dir=str(output / "profiles" / profile.id),
                benchmark_completed=0,
                benchmark_failed=1,
                error=str(exc),
            )
            results.append(result)
            if fail_fast:
                break

    artifact_path = output / "sparring_suite.json"
    summary = SparringSuiteSummary(
        schema_version=SPARRING_SUITE_SCHEMA_VERSION,
        name="opennego_strategy_sparring",
        execution_mode=SPARRING_EXECUTION_MODE,
        output_dir=str(output),
        config_path=str(config_path),
        registry_path=str(registry_path),
        user_role=normalized_user_role,
        opponent_role=opponent_role,
        total_profiles=len(profiles),
        completed=sum(1 for result in results if result.status == "completed"),
        failed=sum(1 for result in results if result.status == "failed"),
        results=tuple(results),
        artifact_path=str(artifact_path),
    )
    write_json(artifact_path, summary)
    return summary


def _run_profile_sparring(
    *,
    profile: StrategyProfile,
    output_dir: Path,
    config_path: str | Path,
    registry_path: str | Path,
    user_role: Role,
    learning_tool_regime: str,
) -> SparringOpponentResult:
    benchmark = run_experiment_config(config_path, output_dir=output_dir / "benchmark")
    learning_run = _select_completed_run(benchmark.runs, learning_tool_regime)
    report = generate_battle_report(
        learning_run.output_dir,
        user_role=user_role,
        npc_registry_path=registry_path,
        opponent_profile_id=profile.id,
    )
    battle_report_path = output_dir / "battle_report.json"
    write_json(battle_report_path, report)
    return _opponent_result(
        profile=profile,
        benchmark=benchmark,
        learning_run=learning_run,
        report=report,
        battle_report_path=battle_report_path,
    )


def _opponent_result(
    *,
    profile: StrategyProfile,
    benchmark: ExperimentSummary,
    learning_run: RunRecord,
    report: BattleReport,
    battle_report_path: Path,
) -> SparringOpponentResult:
    return SparringOpponentResult(
        profile_id=profile.id,
        profile_name=profile.name,
        profile_role=profile.role,
        difficulty=profile.difficulty,
        status="completed",
        benchmark_output_dir=str(Path(benchmark.output_dir)),
        benchmark_completed=benchmark.completed,
        benchmark_failed=benchmark.failed,
        learning_input_dir=learning_run.output_dir,
        battle_report=str(battle_report_path),
        outcome=report.outcome,
        deal_price=report.deal_price,
        policy_score=report.score,
        failure_modes=report.failure_modes,
        lesson_ids=tuple(lesson.id for lesson in report.lessons),
    )


def _select_profiles(
    profiles: Sequence[StrategyProfile],
    *,
    opponent_role: Role,
    requested_ids: Sequence[str] | None,
) -> tuple[StrategyProfile, ...]:
    by_id = {profile.id: profile for profile in profiles}
    if requested_ids:
        selected = []
        for profile_id in requested_ids:
            try:
                profile = by_id[profile_id]
            except KeyError as exc:
                raise KeyError(f"Unknown strategy profile: {profile_id}") from exc
            if profile.role != opponent_role:
                raise ValueError(
                    f"{profile_id}: expected {opponent_role.value} profile, "
                    f"got {profile.role.value}"
                )
            selected.append(profile)
        return tuple(selected)
    selected = tuple(profile for profile in profiles if profile.role == opponent_role)
    if not selected:
        raise ValueError(f"No {opponent_role.value} profiles found in strategy registry")
    return selected


def _select_completed_run(records: Sequence[RunRecord], tool_regime: str) -> RunRecord:
    for record in records:
        if record.status == "completed" and f"-{tool_regime}-" in record.run_id:
            return record
    completed = [record for record in records if record.status == "completed"]
    if completed:
        return completed[0]
    raise ValueError("Sparring suite requires at least one completed benchmark run")


def _opponent_role(role: Role) -> Role:
    return Role.SELLER if role == Role.BUYER else Role.BUYER
