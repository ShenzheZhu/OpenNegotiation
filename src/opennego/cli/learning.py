"""Policy-learning commands: sparring, strategy evolution, and training loops."""

from __future__ import annotations

import argparse
from pathlib import Path

from opennego.agent_loader import (
    AgentLoadError,
    load_sparring_user_agent_factory,
    parse_agent_params,
)
from opennego.agents import make_llm_buyer, make_llm_seller, make_profile_llm_agent
from opennego.artifacts import to_jsonable
from opennego.evolution import (
    StrategyEvolutionError,
    load_strategy_candidate,
    write_strategy_candidate,
    write_strategy_comparison,
)
from opennego.learning import (
    DEFAULT_NPC_REGISTRY_PATH,
    registry_listing,
    write_battle_report,
)
from opennego.runner import ConfigValidationError
from opennego.schema import Role
from opennego.sparring import run_sparring_suite
from opennego.sparring_report import write_sparring_report
from opennego.strategy_config import (
    StrategyConfigError,
    load_strategy_config,
    write_strategy_config,
)
from opennego.training import run_training_loop
from opennego.training_adapter import (
    TrainingAdapterError,
    validate_training_adapter_package,
    write_training_adapter_package,
)

from . import common


def strategies_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List OpenNegotiation NPC strategy profiles."
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_NPC_REGISTRY_PATH),
        help="Path to an NPC strategy registry JSON file.",
    )
    parser.add_argument(
        "--role",
        choices=("buyer", "seller"),
        help="Optional role filter.",
    )
    args = parser.parse_args(argv)

    try:
        payload = registry_listing(args.registry, role=args.role)
    except (OSError, ValueError) as exc:
        return common.print_error(exc)
    common.print_json(payload)
    return 0


def learn_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a policy-learning battle report from run artifacts."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing one completed benchmark run artifact set.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the battle report JSON.",
    )
    parser.add_argument(
        "--user-role",
        default="buyer",
        choices=("buyer", "seller"),
        help="Role of the user-owned agent to optimize.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_NPC_REGISTRY_PATH),
        help="Path to an NPC strategy registry JSON file.",
    )
    parser.add_argument(
        "--opponent-profile",
        help="Optional NPC strategy profile id for the counterparty.",
    )
    parser.add_argument(
        "--coach",
        default="rules",
        choices=("rules", "llm"),
        help="Coach implementation. 'rules' is the deterministic no-key default.",
    )
    parser.add_argument(
        "--coach-model",
        help="LiteLLM model id for --coach llm (required when --coach llm).",
    )
    parser.add_argument(
        "--coach-temperature",
        type=float,
        default=0.0,
        help="Temperature for --coach llm.",
    )
    parser.add_argument(
        "--coach-max-tokens",
        type=int,
        default=1536,
        help="Max tokens for --coach llm calls.",
    )
    args = parser.parse_args(argv)

    coach = None
    if args.coach == "llm":
        if not args.coach_model:
            return common.print_error("--coach llm requires --coach-model")
        preflight_error = common.llm_preflight_error((args.coach_model,))
        if preflight_error is not None:
            return common.print_error(preflight_error)
        from opennego.coaching import LLMCoach

        coach = LLMCoach(
            llm=common.make_litellm_gateway(),
            model=args.coach_model,
            temperature=args.coach_temperature,
            max_tokens=args.coach_max_tokens,
        )

    try:
        output_path = write_battle_report(
            args.input_dir,
            args.output,
            user_role=args.user_role,
            npc_registry_path=args.registry,
            opponent_profile_id=args.opponent_profile,
            coach=coach,
        )
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        return common.print_error(exc)

    common.print_json({"battle_report": str(output_path), "coach": args.coach})
    return 0


def evolve_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a versioned strategy candidate from a battle report."
    )
    parser.add_argument(
        "--battle-report",
        required=True,
        help="Path to a policy-learning battle_report.json artifact.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the strategy candidate JSON.",
    )
    parser.add_argument(
        "--parent-strategy-id",
        default="user_strategy_v0",
        help="Stable id of the strategy being patched.",
    )
    parser.add_argument(
        "--iteration",
        type=int,
        default=1,
        help="Positive strategy iteration number.",
    )
    args = parser.parse_args(argv)

    try:
        output_path = write_strategy_candidate(
            args.battle_report,
            args.output,
            parent_strategy_id=args.parent_strategy_id,
            iteration=args.iteration,
        )
    except (OSError, StrategyEvolutionError) as exc:
        return common.print_error(exc)

    common.print_json({"strategy_candidate": str(output_path)})
    return 0


def apply_strategy_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply a strategy candidate into a versioned strategy config."
    )
    parser.add_argument(
        "--candidate",
        required=True,
        help="Path to an opennego.strategy_evolution.v1 strategy candidate.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the opennego.strategy_config.v1 JSON artifact.",
    )
    parser.add_argument(
        "--base-config",
        help="Optional prior strategy_config.json to preserve base prompt and lineage.",
    )
    parser.add_argument(
        "--strategy-id",
        help="Optional id for the resulting strategy config.",
    )
    args = parser.parse_args(argv)

    try:
        output_path = write_strategy_config(
            args.candidate,
            args.output,
            base_config_path=args.base_config,
            strategy_id=args.strategy_id,
        )
        config = load_strategy_config(output_path)
    except (OSError, StrategyEvolutionError, StrategyConfigError) as exc:
        return common.print_error(exc)

    common.print_json(
        {
            "strategy_config": str(output_path),
            "strategy_id": config.strategy_id,
            "version": config.version,
            "role": config.role.value,
        }
    )
    return 0


def export_training_adapter_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a strategy config as an external training adapter package."
    )
    parser.add_argument(
        "--strategy-config",
        required=True,
        help="Path to an opennego.strategy_config.v1 artifact.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the opennego.external_training_adapter.v1 package.",
    )
    parser.add_argument(
        "--agent-kind",
        required=True,
        help="External agent kind or registry key expected to consume the package.",
    )
    parser.add_argument("--adapter-id", help="Optional stable adapter id.")
    parser.add_argument(
        "--integration-mode",
        default="prompt_config",
        choices=("prompt_config", "agent_factory_params"),
        help="How the external agent should consume the adapter payload.",
    )
    parser.add_argument(
        "--entrypoint-hint",
        help="Optional local entrypoint hint such as PATH:CALLABLE.",
    )
    args = parser.parse_args(argv)

    try:
        package = write_training_adapter_package(
            args.strategy_config,
            args.output,
            agent_kind=args.agent_kind,
            integration_mode=args.integration_mode,
            adapter_id=args.adapter_id,
            entrypoint_hint=args.entrypoint_hint,
        )
    except (OSError, StrategyConfigError, TrainingAdapterError) as exc:
        return common.print_error(exc)

    common.print_json(
        {
            "training_adapter": args.output,
            "adapter_id": package.adapter_id,
            "agent_kind": package.agent_kind,
            "role": package.role.value,
            "strategy_id": package.strategy_id,
            "strategy_version": package.strategy_version,
        }
    )
    return 0


def validate_training_adapter_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an external OpenNegotiation training adapter package."
    )
    parser.add_argument(
        "--adapter",
        required=True,
        help="Path to an opennego.external_training_adapter.v1 package.",
    )
    args = parser.parse_args(argv)

    result = validate_training_adapter_package(args.adapter)
    common.print_json(to_jsonable(result))
    return 0 if result.status == "passed" else 1


def compare_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two policy-learning battle reports."
    )
    parser.add_argument(
        "--before",
        required=True,
        help="Battle report before applying a strategy candidate.",
    )
    parser.add_argument(
        "--after",
        required=True,
        help="Battle report after rerunning with a strategy candidate.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the strategy comparison JSON.",
    )
    args = parser.parse_args(argv)

    try:
        output_path = write_strategy_comparison(
            args.before,
            args.after,
            args.output,
        )
    except (OSError, StrategyEvolutionError) as exc:
        return common.print_error(exc)

    common.print_json({"strategy_comparison": str(output_path)})
    return 0


def train_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a no-key sparring, strategy patch, and rerun loop."
    )
    parser.add_argument(
        "--output-dir",
        default="runs/training_loop",
        help="Directory for baseline, rerun, candidate, comparison, and summary artifacts.",
    )
    parser.add_argument(
        "--config",
        default="configs/real_market_demo.yaml",
        help="Experiment config used for sparring slices.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_NPC_REGISTRY_PATH),
        help="Path to an NPC strategy registry JSON file.",
    )
    parser.add_argument(
        "--user-role",
        default="buyer",
        choices=("buyer", "seller"),
        help="Role of the user-owned agent to optimize.",
    )
    parser.add_argument(
        "--opponent-profile",
        action="append",
        dest="opponent_profiles",
        help=(
            "NPC profile id to include in baseline sparring. Repeat for multiple "
            "profiles. The loop reruns the lowest-scoring completed profile."
        ),
    )
    parser.add_argument(
        "--learning-tool-regime",
        default="no_tools",
        help="Completed run tool regime to diagnose for policy learning.",
    )
    parser.add_argument(
        "--parent-strategy-id",
        default="user_strategy_v0",
        help="Stable id of the strategy being patched.",
    )
    parser.add_argument(
        "--iteration",
        type=int,
        default=1,
        help="Positive strategy iteration number.",
    )
    parser.add_argument("--no-fail-fast", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = run_training_loop(
            output_dir=args.output_dir,
            config_path=args.config,
            registry_path=args.registry,
            user_role=args.user_role,
            opponent_profile_ids=args.opponent_profiles,
            learning_tool_regime=args.learning_tool_regime,
            parent_strategy_id=args.parent_strategy_id,
            iteration=args.iteration,
            fail_fast=not args.no_fail_fast,
        )
    except (OSError, ValueError, KeyError, ConfigValidationError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(summary))
    return 0 if summary.status == "completed" else 1


def spar_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a no-key strategy sparring suite against NPC profiles."
    )
    parser.add_argument(
        "--output-dir",
        default="runs/sparring_suite",
        help="Directory for per-profile runs and sparring_suite.json.",
    )
    parser.add_argument(
        "--config",
        default="configs/real_market_demo.yaml",
        help="Experiment config used for each sparring slice.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_NPC_REGISTRY_PATH),
        help="Path to an NPC strategy registry JSON file.",
    )
    parser.add_argument(
        "--user-role",
        default="buyer",
        choices=("buyer", "seller"),
        help="Role of the user-owned agent to optimize.",
    )
    parser.add_argument(
        "--opponent-profile",
        action="append",
        dest="opponent_profiles",
        help=(
            "NPC profile id to include. Repeat for multiple profiles. "
            "Defaults to every opposite-role profile."
        ),
    )
    parser.add_argument(
        "--user-strategy",
        help="Optional strategy_candidate.json artifact to apply to the user agent.",
    )
    parser.add_argument(
        "--user-agent-factory",
        metavar="PATH:CALLABLE",
        help=(
            "Load a local (role, params) AgentPort factory for the user agent."
        ),
    )
    parser.add_argument(
        "--user-agent-kind",
        help="Manifest kind label for --user-agent-factory.",
    )
    parser.add_argument(
        "--user-agent-param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Parameter passed to --user-agent-factory. Values use JSON scalar "
            "parsing when possible. May be provided multiple times."
        ),
    )
    parser.add_argument(
        "--user-llm-model",
        help=(
            "Use a LiteLLM-backed user agent. Can consume --user-strategy as "
            "strategy instructions for the live user policy."
        ),
    )
    parser.add_argument(
        "--user-llm-tool-policy",
        default="available",
        choices=("none", "available"),
        help="Tool policy for --user-llm-model.",
    )
    parser.add_argument(
        "--user-llm-temperature",
        type=float,
        default=0.0,
        help="Temperature for --user-llm-model.",
    )
    parser.add_argument(
        "--user-llm-max-tokens",
        type=int,
        default=512,
        help="Max tokens for --user-llm-model calls.",
    )
    parser.add_argument(
        "--opponent-llm-model",
        help=(
            "Use a LiteLLM-backed profile NPC for the selected opponent "
            "profile(s). Requires explicit --opponent-profile."
        ),
    )
    parser.add_argument(
        "--opponent-llm-tool-policy",
        default="available",
        choices=("none", "available"),
        help="Tool policy for --opponent-llm-model profile NPCs.",
    )
    parser.add_argument(
        "--opponent-llm-temperature",
        type=float,
        default=0.0,
        help="Temperature for --opponent-llm-model profile NPCs.",
    )
    parser.add_argument(
        "--opponent-llm-max-tokens",
        type=int,
        default=512,
        help="Max tokens for --opponent-llm-model profile NPC calls.",
    )
    parser.add_argument(
        "--learning-tool-regime",
        default="no_tools",
        help="Completed run tool regime to diagnose for policy learning.",
    )
    parser.add_argument(
        "--report",
        help="Optional HTML report path for the generated sparring suite.",
    )
    parser.add_argument("--no-fail-fast", action="store_true")
    args = parser.parse_args(argv)

    try:
        user_agent_factory = None
        user_agent_kind = None
        user_strategy_consumed_by_factory = False
        if args.user_agent_factory and args.user_llm_model:
            raise AgentLoadError(
                "--user-agent-factory and --user-llm-model cannot both be provided"
            )
        if args.user_agent_factory:
            user_agent_factory = load_sparring_user_agent_factory(
                args.user_agent_factory,
                params=parse_agent_params(args.user_agent_param),
            )
            user_agent_kind = args.user_agent_kind or "module_user_agent"
        elif args.user_llm_model:
            if not args.opponent_profiles:
                raise AgentLoadError(
                    "--user-llm-model requires at least one --opponent-profile "
                    "to bound live provider calls"
                )
            if args.user_agent_param:
                raise AgentLoadError(
                    "--user-agent-param requires --user-agent-factory"
                )
            if args.user_agent_kind:
                raise AgentLoadError(
                    "--user-agent-kind requires --user-agent-factory"
                )
            preflight_error = common.llm_preflight_error((args.user_llm_model,))
            if preflight_error is not None:
                raise AgentLoadError(preflight_error)
            user_agent_factory = _user_litellm_agent_factory(
                model=args.user_llm_model,
                tool_policy=args.user_llm_tool_policy,
                temperature=args.user_llm_temperature,
                max_tokens=args.user_llm_max_tokens,
                strategy_path=args.user_strategy,
            )
            user_agent_kind = f"litellm_user_agent:{args.user_llm_model}"
            user_strategy_consumed_by_factory = args.user_strategy is not None
        elif args.user_agent_param:
            raise AgentLoadError(
                "--user-agent-param requires --user-agent-factory"
            )
        elif args.user_agent_kind:
            raise AgentLoadError(
                "--user-agent-kind requires --user-agent-factory"
            )
        opponent_agent_factory = None
        opponent_agent_kind = None
        if args.opponent_llm_model:
            if not args.opponent_profiles:
                raise AgentLoadError(
                    "--opponent-llm-model requires at least one "
                    "--opponent-profile to bound live provider calls"
                )
            preflight_error = common.llm_preflight_error((args.opponent_llm_model,))
            if preflight_error is not None:
                raise AgentLoadError(preflight_error)
            opponent_agent_factory = _profile_litellm_opponent_factory(
                model=args.opponent_llm_model,
                tool_policy=args.opponent_llm_tool_policy,
                temperature=args.opponent_llm_temperature,
                max_tokens=args.opponent_llm_max_tokens,
            )
            opponent_agent_kind = f"litellm_profile_npc:{args.opponent_llm_model}"
        summary = run_sparring_suite(
            output_dir=args.output_dir,
            config_path=args.config,
            registry_path=args.registry,
            user_role=args.user_role,
            opponent_profile_ids=args.opponent_profiles,
            user_strategy_path=args.user_strategy,
            user_agent_factory=user_agent_factory,
            user_agent_kind=user_agent_kind,
            user_strategy_consumed_by_factory=user_strategy_consumed_by_factory,
            opponent_agent_factory=opponent_agent_factory,
            opponent_agent_kind=opponent_agent_kind,
            learning_tool_regime=args.learning_tool_regime,
            fail_fast=not args.no_fail_fast,
        )
        html_report = (
            write_sparring_report(summary.artifact_path, args.report)
            if args.report
            else None
        )
    except (
        OSError,
        AgentLoadError,
        ValueError,
        KeyError,
        ConfigValidationError,
    ) as exc:
        return common.print_error(exc)

    payload = dict(to_jsonable(summary))
    if html_report is not None:
        payload["html_report"] = str(html_report)
    common.print_json(payload)
    return 0 if summary.failed == 0 else 1


def _profile_litellm_opponent_factory(
    *,
    model: str,
    tool_policy: str,
    temperature: float,
    max_tokens: int | None,
):
    llm = common.make_litellm_gateway()

    def factory(profile):
        return make_profile_llm_agent(
            profile=profile,
            llm=llm,
            model=model,
            tool_policy=tool_policy,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    return factory


def _user_litellm_agent_factory(
    *,
    model: str,
    tool_policy: str,
    temperature: float,
    max_tokens: int | None,
    strategy_path: str | Path | None,
):
    llm = common.make_litellm_gateway()
    strategy = load_strategy_candidate(strategy_path) if strategy_path else None
    strategy_instructions = (
        _user_strategy_system_instructions(strategy) if strategy is not None else None
    )

    def factory(role: Role):
        if strategy is not None and strategy.user_role != role:
            raise ValueError(
                f"user strategy role {strategy.user_role.value!r} does not "
                f"match live user agent role {role.value!r}"
            )
        name = f"llm_user_{role.value}:{model}"
        if role == Role.BUYER:
            return make_llm_buyer(
                llm=llm,
                model=model,
                name=name,
                tool_policy=tool_policy,
                temperature=temperature,
                max_tokens=max_tokens,
                system_instructions=strategy_instructions,
            )
        if role == Role.SELLER:
            return make_llm_seller(
                llm=llm,
                model=model,
                name=name,
                tool_policy=tool_policy,
                temperature=temperature,
                max_tokens=max_tokens,
                system_instructions=strategy_instructions,
            )
        raise ValueError(f"unsupported user role: {role.value}")

    return factory


def _user_strategy_system_instructions(strategy) -> str:
    lesson_ids = ", ".join(strategy.applied_lesson_ids) or "none"
    patches = "\n".join(f"- {patch}" for patch in strategy.applied_patches)
    if not patches:
        patches = "- none"
    return (
        f"User strategy candidate id: {strategy.candidate_id}\n"
        f"Parent strategy id: {strategy.parent_strategy_id}\n"
        f"Iteration: {strategy.iteration}\n"
        f"User role: {strategy.user_role.value}\n"
        f"Applied lesson ids: {lesson_ids}\n"
        f"Strategy prompt:\n{strategy.strategy_prompt}\n"
        f"Applied patches:\n{patches}"
    )
