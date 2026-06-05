"""One-command no-key training loop orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import read_json, write_json
from opennego.evolution import write_strategy_candidate, write_strategy_comparison
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH
from opennego.schema import Role
from opennego.sparring import (
    SPARRING_EXECUTION_MODE,
    SparringOpponentResult,
    SparringSuiteSummary,
    run_sparring_suite,
)

TRAINING_LOOP_SCHEMA_VERSION = "opennego.training_loop.v1"
TRAINING_LOOP_EXECUTION_MODE = "sparring_strategy_evolution_v1"


@dataclass(frozen=True)
class TrainingLoopSummary:
    schema_version: str
    status: str
    execution_mode: str
    output_dir: str
    config_path: str
    registry_path: str
    user_role: Role
    requested_opponent_profile_ids: tuple[str, ...]
    selected_profile_id: str
    selected_battle_report: str
    baseline_sparring_artifact: str
    baseline_completed: int
    baseline_failed: int
    strategy_candidate: str
    rerun_sparring_artifact: str
    rerun_battle_report: str
    rerun_completed: int
    rerun_failed: int
    strategy_comparison: str
    comparison_status: str
    score_delta: float
    parent_strategy_id: str
    iteration: int
    shared_runtime_contract: Mapping[str, Any]
    artifact_path: str


def run_training_loop(
    *,
    output_dir: str | Path = "runs/training_loop",
    config_path: str | Path = "configs/real_market_demo.yaml",
    registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    user_role: Role | str = Role.BUYER,
    opponent_profile_ids: Sequence[str] | None = None,
    learning_tool_regime: str = "no_tools",
    parent_strategy_id: str = "user_strategy_v0",
    iteration: int = 1,
    fail_fast: bool = True,
) -> TrainingLoopSummary:
    """Run baseline sparring, generate a patch, rerun, and compare outcomes."""

    output = Path(output_dir)
    normalized_role = Role(user_role)
    requested_profiles = tuple(opponent_profile_ids or ())
    baseline = run_sparring_suite(
        output_dir=output / "baseline",
        config_path=config_path,
        registry_path=registry_path,
        user_role=normalized_role,
        opponent_profile_ids=requested_profiles or None,
        learning_tool_regime=learning_tool_regime,
        fail_fast=fail_fast,
    )
    selected = _select_training_result(baseline)
    if selected.battle_report is None:
        raise ValueError(f"{selected.profile_id}: completed sparring has no battle report")

    candidate_path = output / "strategy_candidate.json"
    write_strategy_candidate(
        selected.battle_report,
        candidate_path,
        parent_strategy_id=parent_strategy_id,
        iteration=iteration,
    )

    rerun = run_sparring_suite(
        output_dir=output / "rerun",
        config_path=config_path,
        registry_path=registry_path,
        user_role=normalized_role,
        opponent_profile_ids=(selected.profile_id,),
        user_strategy_path=candidate_path,
        learning_tool_regime=learning_tool_regime,
        fail_fast=fail_fast,
    )
    rerun_result = _result_for_profile(rerun, selected.profile_id)
    if rerun_result.battle_report is None:
        raise ValueError(f"{selected.profile_id}: rerun has no battle report")

    comparison_path = output / "strategy_comparison.json"
    write_strategy_comparison(
        selected.battle_report,
        rerun_result.battle_report,
        comparison_path,
    )
    comparison = read_json(comparison_path)
    artifact_path = output / "training_loop.json"
    summary = TrainingLoopSummary(
        schema_version=TRAINING_LOOP_SCHEMA_VERSION,
        status="completed",
        execution_mode=TRAINING_LOOP_EXECUTION_MODE,
        output_dir=str(output),
        config_path=str(config_path),
        registry_path=str(registry_path),
        user_role=normalized_role,
        requested_opponent_profile_ids=requested_profiles,
        selected_profile_id=selected.profile_id,
        selected_battle_report=selected.battle_report,
        baseline_sparring_artifact=baseline.artifact_path,
        baseline_completed=baseline.completed,
        baseline_failed=baseline.failed,
        strategy_candidate=str(candidate_path),
        rerun_sparring_artifact=rerun.artifact_path,
        rerun_battle_report=rerun_result.battle_report,
        rerun_completed=rerun.completed,
        rerun_failed=rerun.failed,
        strategy_comparison=str(comparison_path),
        comparison_status=str(comparison.get("status", "unknown")),
        score_delta=float(comparison.get("score_delta", 0.0)),
        parent_strategy_id=parent_strategy_id,
        iteration=iteration,
        shared_runtime_contract={
            "baseline_execution_mode": baseline.execution_mode,
            "rerun_execution_mode": rerun.execution_mode,
            "sparring_execution_mode": SPARRING_EXECUTION_MODE,
            "orchestrator": "opennego.sparring.run_sparring_suite",
            "separate_prompt_simulator": False,
            "artifact_backed": True,
        },
        artifact_path=str(artifact_path),
    )
    write_json(artifact_path, summary)
    return summary


def _select_training_result(summary: SparringSuiteSummary) -> SparringOpponentResult:
    completed = tuple(
        result
        for result in summary.results
        if result.status == "completed" and result.battle_report is not None
    )
    if not completed:
        raise ValueError("training loop requires at least one completed sparring report")
    return min(
        completed,
        key=lambda result: (
            result.policy_score if result.policy_score is not None else 1.0,
            -len(result.failure_modes),
            -len(result.lesson_ids),
            result.profile_id,
        ),
    )


def _result_for_profile(
    summary: SparringSuiteSummary,
    profile_id: str,
) -> SparringOpponentResult:
    for result in summary.results:
        if result.profile_id == profile_id and result.status == "completed":
            return result
    raise ValueError(f"{profile_id}: missing completed rerun sparring result")
