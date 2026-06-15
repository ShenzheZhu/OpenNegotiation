"""One-command no-key training loop orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import random

from opennego.artifacts import read_json, write_json
from opennego.evolution import write_strategy_candidate, write_strategy_comparison
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH, load_strategy_registry
from opennego.schema import Role
from opennego.sparring import (
    SPARRING_EXECUTION_MODE,
    SparringOpponentResult,
    SparringSuiteSummary,
    run_sparring_suite,
)
from opennego.strategy_config import write_strategy_config

TRAINING_LOOP_SCHEMA_VERSION = "opennego.training_loop.v1"
TRAINING_LOOP_EXECUTION_MODE = "sparring_strategy_evolution_v1"


def _is_safety_profile(profile) -> bool:
    return "safety" in set(profile.tags) or profile.difficulty == "safety"


def split_opponent_roster(
    *,
    registry_path: str | Path,
    user_role: Role,
    seed: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split opposite-role NPC profiles into train and held-out id sets.

    The split is deterministic in ``seed``. Safety (scam) archetypes always
    appear in both sets: refusal must hold whether or not the strategy trained
    against that exact scam. Non-safety profiles are shuffled and dealt
    evenly, with the train set taking the extra profile on odd counts.
    """

    registry = load_strategy_registry(registry_path)
    opponent_role = Role.SELLER if user_role == Role.BUYER else Role.BUYER
    profiles = registry.for_role(opponent_role)
    safety = [p.id for p in profiles if _is_safety_profile(p)]
    pool = [p.id for p in profiles if not _is_safety_profile(p)]
    random.Random(f"holdout:{seed}:{user_role.value}").shuffle(pool)
    midpoint = (len(pool) + 1) // 2
    train = tuple(pool[:midpoint]) + tuple(safety)
    heldout = tuple(pool[midpoint:]) + tuple(safety)
    return train, heldout


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
    strategy_config: str
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
    generalization: Mapping[str, Any] | None = None


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
    holdout_validation: bool = False,
    holdout_seed: int = 0,
) -> TrainingLoopSummary:
    """Run baseline sparring, generate a patch, rerun, and compare outcomes.

    With ``holdout_validation`` the loop splits the opposite-role roster into
    train and held-out sets, picks the patch target from the train set only,
    reruns the candidate across the whole roster, and reports per-set
    generalization so an overfit (train-only) candidate is visible.
    """

    output = Path(output_dir)
    normalized_role = Role(user_role)
    requested_profiles = tuple(opponent_profile_ids or ())

    train_ids: tuple[str, ...] = ()
    heldout_ids: tuple[str, ...] = ()
    if holdout_validation:
        train_ids, heldout_ids = split_opponent_roster(
            registry_path=registry_path,
            user_role=normalized_role,
            seed=holdout_seed,
        )
        baseline_profiles: tuple[str, ...] | None = tuple(
            dict.fromkeys(train_ids + heldout_ids)
        )
    else:
        baseline_profiles = requested_profiles or None

    baseline = run_sparring_suite(
        output_dir=output / "baseline",
        config_path=config_path,
        registry_path=registry_path,
        user_role=normalized_role,
        opponent_profile_ids=baseline_profiles,
        learning_tool_regime=learning_tool_regime,
        fail_fast=fail_fast,
    )
    selection_pool = set(train_ids) if holdout_validation else None
    selected = _select_training_result(baseline, restrict_to=selection_pool)
    if selected.battle_report is None:
        raise ValueError(f"{selected.profile_id}: completed sparring has no battle report")

    candidate_path = output / "strategy_candidate.json"
    write_strategy_candidate(
        selected.battle_report,
        candidate_path,
        parent_strategy_id=parent_strategy_id,
        iteration=iteration,
    )

    rerun_profiles = baseline_profiles if holdout_validation else (selected.profile_id,)
    rerun = run_sparring_suite(
        output_dir=output / "rerun",
        config_path=config_path,
        registry_path=registry_path,
        user_role=normalized_role,
        opponent_profile_ids=rerun_profiles,
        user_strategy_path=candidate_path,
        learning_tool_regime=learning_tool_regime,
        fail_fast=fail_fast,
    )
    rerun_result = _result_for_profile(rerun, selected.profile_id)
    if rerun_result.battle_report is None:
        raise ValueError(f"{selected.profile_id}: rerun has no battle report")

    generalization = None
    if holdout_validation:
        generalization = _generalization(
            baseline=baseline,
            rerun=rerun,
            train_ids=train_ids,
            heldout_ids=heldout_ids,
        )
        _stamp_generalization_verdict(candidate_path, generalization["verdict"])

    strategy_config_path = output / "strategy_config.json"
    write_strategy_config(candidate_path, strategy_config_path)

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
        strategy_config=str(strategy_config_path),
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
        generalization=generalization,
    )
    write_json(artifact_path, summary)
    return summary


def _select_training_result(
    summary: SparringSuiteSummary,
    *,
    restrict_to: set[str] | None = None,
) -> SparringOpponentResult:
    completed = tuple(
        result
        for result in summary.results
        if result.status == "completed"
        and result.battle_report is not None
        and (restrict_to is None or result.profile_id in restrict_to)
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


def _generalization(
    *,
    baseline: SparringSuiteSummary,
    rerun: SparringSuiteSummary,
    train_ids: tuple[str, ...],
    heldout_ids: tuple[str, ...],
) -> Mapping[str, Any]:
    """Per-set score/deal-rate deltas and an overfitting verdict.

    train_only means the candidate improved on the profiles it was patched
    against but not on held-out opponents — the overfitting signal apply-
    strategy guards against.
    """

    before = {r.profile_id: r for r in baseline.results if r.status == "completed"}
    after = {r.profile_id: r for r in rerun.results if r.status == "completed"}

    def _set_stats(ids: tuple[str, ...]) -> Mapping[str, Any]:
        shared = [pid for pid in dict.fromkeys(ids) if pid in before and pid in after]
        score_deltas = [
            (after[pid].policy_score or 0.0) - (before[pid].policy_score or 0.0)
            for pid in shared
        ]
        deal_delta = _deal_rate(after, shared) - _deal_rate(before, shared)
        return {
            "profile_ids": shared,
            "profile_count": len(shared),
            "mean_score_delta": round(_mean(score_deltas), 4),
            "deal_rate_delta": round(deal_delta, 4),
        }

    train_stats = _set_stats(train_ids)
    heldout_stats = _set_stats(heldout_ids)
    train_delta = train_stats["mean_score_delta"]
    heldout_delta = heldout_stats["mean_score_delta"]
    if train_delta <= 0:
        verdict = "regressed"
    elif heldout_delta < 0:
        verdict = "train_only"
    else:
        verdict = "improved"
    return {
        "verdict": verdict,
        "train": train_stats,
        "held_out": heldout_stats,
    }


def _stamp_generalization_verdict(candidate_path: Path, verdict: str) -> None:
    candidate = read_json(candidate_path)
    metadata = dict(candidate.get("metadata", {}))
    metadata["generalization_verdict"] = verdict
    candidate["metadata"] = metadata
    write_json(candidate_path, candidate)


def _deal_rate(
    results: Mapping[str, SparringOpponentResult],
    ids: Sequence[str],
) -> float:
    if not ids:
        return 0.0
    deals = sum(1 for pid in ids if results[pid].outcome == "deal")
    return deals / len(ids)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _result_for_profile(
    summary: SparringSuiteSummary,
    profile_id: str,
) -> SparringOpponentResult:
    for result in summary.results:
        if result.profile_id == profile_id and result.status == "completed":
            return result
    raise ValueError(f"{profile_id}: missing completed rerun sparring result")
