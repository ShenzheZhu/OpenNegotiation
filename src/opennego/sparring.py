"""No-key strategy sparring suite orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Sequence

from opennego.agents import make_profile_agent_pair
from opennego.artifacts import write_json, write_run_artifacts
from opennego.environment import NegotiationEnvironment
from opennego.evolution import StrategyCandidate, load_strategy_candidate
from opennego.learning import (
    DEFAULT_NPC_REGISTRY_PATH,
    BattleReport,
    StrategyProfile,
    generate_battle_report,
    load_strategy_registry,
)
from opennego.runner import (
    ConfigValidationError,
    ExperimentConfig,
    ExperimentSummary,
    PreparedRun,
    RunRecord,
    ToolRegimeConfig,
    ToolSpec,
    load_experiment_config,
    prepare_runs,
)
from opennego.ports import AgentPort
from opennego.schema import Role

SPARRING_SUITE_SCHEMA_VERSION = "opennego.sparring_suite.v1"
SPARRING_EXECUTION_MODE = "profile_backed_fixture_sparring"
UserAgentFactory = Callable[[Role], AgentPort]
OpponentAgentFactory = Callable[[StrategyProfile], AgentPort]


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
    user_strategy_candidate_id: str | None = None
    user_agent_kind: str | None = None
    opponent_agent_kind: str | None = None
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
    user_strategy_candidate_id: str | None
    user_strategy_path: str | None
    user_agent_kind: str | None
    opponent_agent_kind: str | None
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
    user_strategy_path: str | Path | None = None,
    user_agent_factory: UserAgentFactory | None = None,
    user_agent_kind: str | None = None,
    opponent_agent_factory: OpponentAgentFactory | None = None,
    opponent_agent_kind: str | None = None,
    learning_tool_regime: str = "no_tools",
    fail_fast: bool = True,
) -> SparringSuiteSummary:
    """Run deterministic sparring diagnostics for selected strategy profiles."""

    output = Path(output_dir)
    registry = load_strategy_registry(registry_path)
    normalized_user_role = Role(user_role)
    if user_strategy_path is not None and user_agent_factory is not None:
        raise ValueError(
            "user_strategy_path and user_agent_factory cannot both be provided"
        )
    normalized_user_agent_kind = None
    if user_agent_factory is not None:
        normalized_user_agent_kind = user_agent_kind or "custom_user_agent"
    normalized_opponent_agent_kind = None
    if opponent_agent_factory is not None:
        normalized_opponent_agent_kind = (
            opponent_agent_kind or "custom_profile_agent"
        )
    if user_agent_factory is not None:
        _create_user_agent(
            user_agent_factory,
            role=normalized_user_role,
            kind=normalized_user_agent_kind,
        )
    user_strategy = (
        load_strategy_candidate(user_strategy_path)
        if user_strategy_path is not None
        else None
    )
    if user_strategy is not None and user_strategy.user_role != normalized_user_role:
        raise ValueError(
            f"user strategy role {user_strategy.user_role.value!r} does not "
            f"match user_role {normalized_user_role.value!r}"
        )
    opponent_role = _opponent_role(normalized_user_role)
    profiles = _select_profiles(
        registry.profiles,
        opponent_role=opponent_role,
        requested_ids=opponent_profile_ids,
    )
    if opponent_agent_factory is not None:
        for profile in profiles:
            _create_opponent_agent(
                opponent_agent_factory,
                profile=profile,
                kind=normalized_opponent_agent_kind,
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
                    user_strategy=user_strategy,
                    user_agent_factory=user_agent_factory,
                    user_agent_kind=normalized_user_agent_kind,
                    opponent_agent_factory=opponent_agent_factory,
                    opponent_agent_kind=normalized_opponent_agent_kind,
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
                user_strategy_candidate_id=(
                    user_strategy.candidate_id if user_strategy else None
                ),
                user_agent_kind=normalized_user_agent_kind,
                opponent_agent_kind=normalized_opponent_agent_kind,
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
        user_strategy_candidate_id=user_strategy.candidate_id if user_strategy else None,
        user_strategy_path=str(user_strategy_path) if user_strategy_path else None,
        user_agent_kind=normalized_user_agent_kind,
        opponent_agent_kind=normalized_opponent_agent_kind,
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
    user_strategy: StrategyCandidate | None,
    user_agent_factory: UserAgentFactory | None,
    user_agent_kind: str | None,
    opponent_agent_factory: OpponentAgentFactory | None,
    opponent_agent_kind: str | None,
    learning_tool_regime: str,
) -> SparringOpponentResult:
    benchmark = _run_profile_benchmark(
        profile=profile,
        output_dir=output_dir / "benchmark",
        config_path=config_path,
        user_role=user_role,
        user_strategy=user_strategy,
        user_agent_factory=user_agent_factory,
        user_agent_kind=user_agent_kind,
        opponent_agent_factory=opponent_agent_factory,
        opponent_agent_kind=opponent_agent_kind,
    )
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
        user_strategy=user_strategy,
        user_agent_kind=user_agent_kind,
        opponent_agent_kind=opponent_agent_kind,
    )


def _opponent_result(
    *,
    profile: StrategyProfile,
    benchmark: ExperimentSummary,
    learning_run: RunRecord,
    report: BattleReport,
    battle_report_path: Path,
    user_strategy: StrategyCandidate | None,
    user_agent_kind: str | None,
    opponent_agent_kind: str | None,
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
        user_strategy_candidate_id=(
            user_strategy.candidate_id if user_strategy else None
        ),
        user_agent_kind=user_agent_kind,
        opponent_agent_kind=opponent_agent_kind,
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


def _run_profile_benchmark(
    *,
    profile: StrategyProfile,
    output_dir: Path,
    config_path: str | Path,
    user_role: Role,
    user_strategy: StrategyCandidate | None,
    user_agent_factory: UserAgentFactory | None,
    user_agent_kind: str | None,
    opponent_agent_factory: OpponentAgentFactory | None,
    opponent_agent_kind: str | None,
) -> ExperimentSummary:
    config = replace(
        load_experiment_config(config_path),
        output_dir=output_dir,
        resume=False,
    )
    prepared_runs = prepare_runs(config)
    records: list[RunRecord] = []
    for prepared_run in prepared_runs:
        try:
            result = _execute_profile_prepared_run(
                prepared_run=prepared_run,
                config=config,
                profile=profile,
                user_role=user_role,
                user_strategy=user_strategy,
                user_agent_factory=user_agent_factory,
                user_agent_kind=user_agent_kind,
                opponent_agent_factory=opponent_agent_factory,
                opponent_agent_kind=opponent_agent_kind,
            )
        except Exception as exc:  # pragma: no cover - CLI failure path
            records.append(
                RunRecord(
                    run_id=prepared_run.run_id,
                    status="failed",
                    output_dir=str(prepared_run.output_dir),
                    error=str(exc),
                )
            )
            if config.fail_fast:
                break
            continue

        records.append(
            RunRecord(
                run_id=prepared_run.run_id,
                status="completed",
                output_dir=str(prepared_run.output_dir),
                outcome=result.outcome,
                deal_price=result.deal_price,
                completed_turns=result.completed_turns,
            )
        )

    return ExperimentSummary(
        name=config.name,
        output_dir=str(config.output_dir),
        total_runs=len(prepared_runs),
        completed=sum(1 for record in records if record.status == "completed"),
        skipped=0,
        failed=sum(1 for record in records if record.status == "failed"),
        runs=tuple(records),
    )


def _execute_profile_prepared_run(
    *,
    prepared_run: PreparedRun,
    config: ExperimentConfig,
    profile: StrategyProfile,
    user_role: Role,
    user_strategy: StrategyCandidate | None,
    user_agent_factory: UserAgentFactory | None,
    user_agent_kind: str | None,
    opponent_agent_factory: OpponentAgentFactory | None,
    opponent_agent_kind: str | None,
):
    buyer, seller = _profile_agent_pair(
        profile=profile,
        user_role=user_role,
        user_strategy=user_strategy,
        user_agent_factory=user_agent_factory,
        user_agent_kind=user_agent_kind,
        opponent_agent_factory=opponent_agent_factory,
        opponent_agent_kind=opponent_agent_kind,
    )
    env = NegotiationEnvironment(
        scenario=prepared_run.scenario,
        buyer=buyer,
        seller=seller,
        tools=prepared_run.tools,
        tool_configs=prepared_run.tool_configs,
        transaction_simulator=prepared_run.transaction_simulator,
    )
    result = env.run()
    write_run_artifacts(
        result=result,
        output_dir=prepared_run.output_dir,
        run_id=prepared_run.run_id,
        scenario_id=prepared_run.scenario_id,
        seed=prepared_run.seed,
        agents={
            "buyer": _agent_manifest(
                buyer,
                profile=profile,
                user_role=user_role,
                user_agent_kind=user_agent_kind,
                opponent_agent_kind=opponent_agent_kind,
            ),
            "seller": _agent_manifest(
                seller,
                profile=profile,
                user_role=user_role,
                user_agent_kind=user_agent_kind,
                opponent_agent_kind=opponent_agent_kind,
            ),
        },
        tool_regime=_tool_regime_manifest(prepared_run.tool_regime),
        metadata={
            "experiment_name": config.name,
            "sparring_execution_mode": SPARRING_EXECUTION_MODE,
            "user_role": user_role.value,
            "opponent_profile_id": profile.id,
            "opponent_profile_name": profile.name,
            "opponent_archetype": profile.archetype,
            "opponent_difficulty": profile.difficulty,
            "user_strategy": _strategy_metadata(user_strategy),
        },
    )
    return result


def _profile_agent_pair(
    *,
    profile: StrategyProfile,
    user_role: Role,
    user_strategy: StrategyCandidate | None,
    user_agent_factory: UserAgentFactory | None,
    user_agent_kind: str | None,
    opponent_agent_factory: OpponentAgentFactory | None,
    opponent_agent_kind: str | None,
):
    user_agent = (
        _create_user_agent(
            user_agent_factory,
            role=user_role,
            kind=user_agent_kind or "custom_user_agent",
        )
        if user_agent_factory is not None
        else None
    )
    profile_agent = (
        _create_opponent_agent(
            opponent_agent_factory,
            profile=profile,
            kind=opponent_agent_kind or "custom_profile_agent",
        )
        if opponent_agent_factory is not None
        else None
    )
    return make_profile_agent_pair(
        profile=profile,
        user_role=user_role,
        user_strategy=user_strategy,
        user_agent=user_agent,
        profile_agent=profile_agent,
    )


def _agent_manifest(
    agent,
    *,
    profile: StrategyProfile,
    user_role: Role,
    user_agent_kind: str | None,
    opponent_agent_kind: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": agent.name,
        "role": agent.role.value,
    }
    if agent.role == profile.role:
        payload.update(
            {
                "kind": opponent_agent_kind or f"strategy_profile_{agent.role.value}",
                "profile_id": profile.id,
                "profile_name": profile.name,
                "archetype": profile.archetype,
                "difficulty": profile.difficulty,
            }
        )
    elif getattr(agent, "strategy_candidate_id", None):
        payload.update(
            {
                "kind": f"strategy_candidate_{agent.role.value}",
                "candidate_id": agent.strategy_candidate_id,
                "parent_strategy_id": agent.parent_strategy_id,
                "applied_lesson_ids": list(agent.applied_lesson_ids),
            }
        )
    elif agent.role == user_role and user_agent_kind is not None:
        payload["kind"] = user_agent_kind
    else:
        payload["kind"] = f"user_{agent.role.value}"
    return payload


def _create_user_agent(
    factory: UserAgentFactory,
    *,
    role: Role,
    kind: str,
) -> AgentPort:
    try:
        agent = factory(role)
    except Exception as exc:
        raise ValueError(f"user_agent_factory {kind!r} failed: {exc}") from exc
    if agent.role != role:
        raise ValueError(
            f"user_agent_factory {kind!r} returned role "
            f"{agent.role.value!r}, expected {role.value!r}"
        )
    if not isinstance(agent.name, str) or not agent.name:
        raise ValueError(f"user_agent_factory {kind!r} returned agent without name")
    if not callable(getattr(agent, "act", None)):
        raise ValueError(
            f"user_agent_factory {kind!r} returned agent without act(context)"
        )
    return agent


def _create_opponent_agent(
    factory: OpponentAgentFactory,
    *,
    profile: StrategyProfile,
    kind: str,
) -> AgentPort:
    try:
        agent = factory(profile)
    except Exception as exc:
        raise ValueError(f"opponent_agent_factory {kind!r} failed: {exc}") from exc
    if agent.role != profile.role:
        raise ValueError(
            f"opponent_agent_factory {kind!r} returned role "
            f"{agent.role.value!r}, expected {profile.role.value!r}"
        )
    if not isinstance(agent.name, str) or not agent.name:
        raise ValueError(
            f"opponent_agent_factory {kind!r} returned agent without name"
        )
    if not callable(getattr(agent, "act", None)):
        raise ValueError(
            f"opponent_agent_factory {kind!r} returned agent without act(context)"
        )
    return agent


def _strategy_metadata(candidate: StrategyCandidate | None) -> dict[str, object]:
    if candidate is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "candidate_id": candidate.candidate_id,
        "parent_strategy_id": candidate.parent_strategy_id,
        "iteration": candidate.iteration,
        "applied_lesson_ids": list(candidate.applied_lesson_ids),
        "source_run_id": candidate.source_run_id,
    }


def _tool_regime_manifest(tool_regime: ToolRegimeConfig) -> dict[str, object]:
    return {
        "id": tool_regime.id,
        "tools": [
            {
                "name": spec.name,
                "kind": spec.kind,
                "source": str(spec.source) if spec.source else None,
                "visibility": spec.visibility,
                "roles": [role.value for role in _tool_roles(spec)],
                "mode": spec.mode,
                "fail_fast": spec.fail_fast,
                "enabled": spec.enabled,
                "metadata": dict(spec.metadata or {}),
            }
            for spec in tool_regime.tools
        ],
        "metadata": dict(tool_regime.metadata or {}),
    }


def _tool_roles(spec: ToolSpec) -> tuple[Role, ...]:
    if spec.roles is not None:
        return spec.roles
    if spec.visibility == "buyer_private":
        return (Role.BUYER,)
    if spec.visibility == "seller_private":
        return (Role.SELLER,)
    return (Role.BUYER, Role.SELLER)
