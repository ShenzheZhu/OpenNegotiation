"""Command-line entry points for OpenNegotiation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

from opennego.agent_loader import (
    AgentLoadError,
    load_agent_factories,
    load_sparring_user_agent_factory,
    parse_agent_params,
)
from opennego.arena import ArenaPlanError, write_arena_plan
from opennego.artifacts import to_jsonable, write_run_artifacts
from opennego.agents import (
    ScriptedSeller,
    ToolAwareBuyer,
    make_llm_buyer,
    make_llm_seller,
    make_profile_llm_agent,
)
from opennego.environment import NegotiationEnvironment
from opennego.evolution import (
    StrategyEvolutionError,
    load_strategy_candidate,
    write_strategy_candidate,
    write_strategy_comparison,
)
from opennego.handoff import run_external_handoff_package
from opennego.learning import (
    DEFAULT_NPC_REGISTRY_PATH,
    registry_listing,
    write_battle_report,
)
from opennego.leaderboard import build_leaderboard, write_leaderboard
from opennego.market_ingestion import MarketIngestionError, ingest_market_data
from opennego.market_sources import (
    MarketSourcePolicyError,
    validate_market_source_policy,
    write_market_source_policy,
)
from opennego.market_validation import validate_market_dataset
from opennego.marketplace import (
    MarketplaceError,
    validate_marketplace_configs,
    write_marketplace_profile,
)
from opennego.model_demo import (
    DEFAULT_MODEL_DEMO_MODELS,
    make_litellm_gateway,
    run_model_demo,
)
from opennego.demo import (
    run_demo,
    run_mvp_demo,
    validate_demo_bundle,
)
from opennego.report import write_demo_report
from opennego.role_swap import run_role_swap_benchmark
from opennego.runner import (
    ConfigValidationError,
    LLM_AGENT_KINDS,
    load_experiment_config,
    run_experiment_config,
)
from opennego.schema import Product, Role, Scenario
from opennego.sparring import run_sparring_suite
from opennego.sparring_report import write_sparring_report
from opennego.strategy_config import (
    StrategyConfigError,
    load_strategy_config,
    write_strategy_config,
)
from opennego.training_adapter import (
    TrainingAdapterError,
    validate_training_adapter_package,
    write_training_adapter_package,
)
from opennego.tools import MarketPriceTool
from opennego.training import run_training_loop


def load_first_product(path: str | Path) -> Product:
    records = json.loads(Path(path).read_text())
    if not records:
        raise ValueError(f"No products found in {path}")
    return Product.from_mapping(records[0])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "run":
        return _run_config_main(argv[1:])
    if argv and argv[0] == "run-models":
        return _run_models_main(argv[1:])
    if argv and argv[0] == "report":
        return _report_main(argv[1:])
    if argv and argv[0] == "strategies":
        return _strategies_main(argv[1:])
    if argv and argv[0] == "learn":
        return _learn_main(argv[1:])
    if argv and argv[0] == "evolve":
        return _evolve_main(argv[1:])
    if argv and argv[0] == "apply-strategy":
        return _apply_strategy_main(argv[1:])
    if argv and argv[0] == "export-training-adapter":
        return _export_training_adapter_main(argv[1:])
    if argv and argv[0] == "validate-training-adapter":
        return _validate_training_adapter_main(argv[1:])
    if argv and argv[0] == "compare":
        return _compare_main(argv[1:])
    if argv and argv[0] == "leaderboard":
        return _leaderboard_main(argv[1:])
    if argv and argv[0] == "arena-plan":
        return _arena_plan_main(argv[1:])
    if argv and argv[0] == "role-swap":
        return _role_swap_main(argv[1:])
    if argv and argv[0] == "marketplace-export":
        return _marketplace_export_main(argv[1:])
    if argv and argv[0] == "validate-marketplace":
        return _validate_marketplace_main(argv[1:])
    if argv and argv[0] == "market-source-policy":
        return _market_source_policy_main(argv[1:])
    if argv and argv[0] == "validate-market-source":
        return _validate_market_source_main(argv[1:])
    if argv and argv[0] == "ingest-market":
        return _ingest_market_main(argv[1:])
    if argv and argv[0] == "ingest-ebay":
        return _ingest_ebay_main(argv[1:])
    if argv and argv[0] == "validate-market":
        return _validate_market_main(argv[1:])
    if argv and argv[0] == "validate-demo":
        return _validate_demo_bundle_main(argv[1:])
    if argv and argv[0] == "validate-demo-bundle":
        return _validate_demo_bundle_main(argv[1:])
    if argv and argv[0] == "demo":
        return _demo_main(argv[1:])
    if argv and argv[0] == "mvp-demo":
        return _demo_main(argv[1:], legacy=True)
    if argv and argv[0] == "handoff":
        return _handoff_main(argv[1:])
    if argv and argv[0] == "train":
        return _train_main(argv[1:])
    if argv and argv[0] == "spar":
        return _spar_main(argv[1:])

    parser = argparse.ArgumentParser(description="Run a deterministic OpenNegotiation smoke demo.")
    parser.add_argument("--products-file", default="examples/data/products.json")
    parser.add_argument("--market-comps-file", default="examples/data/market_comps.json")
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--output-json", help="Optional path for the full run trace.")
    parser.add_argument("--output-dir", help="Optional directory for versioned benchmark artifacts.")
    parser.add_argument("--run-id", help="Run id for benchmark artifacts.")
    parser.add_argument("--seed", type=int, help="Seed recorded in benchmark artifacts.")
    args = parser.parse_args(argv)

    product = load_first_product(args.products_file)
    buyer_budget = float(product.attributes.get("buyer_budget", product.list_price * 0.85))
    scenario = Scenario(
        product=product,
        buyer_budget=buyer_budget,
        seller_reservation_price=product.wholesale_price,
        max_turns=args.max_turns,
    )
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(MarketPriceTool.from_json(args.market_comps_file),),
    )
    result = env.run()
    payload = to_jsonable(result)

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, indent=2) + "\n")
    if args.output_dir:
        run_id = args.run_id or f"smoke-{product.id}"
        paths = write_run_artifacts(
            result=result,
            output_dir=args.output_dir,
            run_id=run_id,
            seed=args.seed,
            agents={
                "buyer": {"name": "tool_aware_buyer", "kind": "scripted"},
                "seller": {"name": "scripted_seller", "kind": "scripted"},
            },
            tool_regime={
                "market_price_search": {
                    "visibility": "buyer_private",
                    "source": str(args.market_comps_file),
                }
            },
        )
    else:
        paths = None

    print(
        json.dumps(
            {
                "outcome": result.outcome,
                "deal_price": result.deal_price,
                "completed_turns": result.completed_turns,
                "metrics": result.metrics,
                "artifacts": str(paths.output_dir) if paths else None,
            },
            indent=2,
        )
    )
    return 0


def _run_config_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an OpenNegotiation experiment config.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an OpenNegotiation experiment config.",
    )
    parser.add_argument("--output-dir", help="Override the config output_dir.")
    parser.add_argument("--resume", dest="resume", action="store_true", default=None)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument(
        "--agent-factory",
        action="append",
        default=[],
        metavar="KIND=PATH:CALLABLE",
        help=(
            "Load a local AgentPort factory for a config agent kind. "
            "May be provided multiple times."
        ),
    )
    args = parser.parse_args(argv)

    try:
        agent_factories = load_agent_factories(args.agent_factory)
        llm_models = _config_llm_models(args.config)
        llm_factory = None
        if llm_models is not None:
            preflight_error = (
                _run_models_preflight_error(llm_models) if llm_models else None
            )
            if preflight_error is not None:
                print(json.dumps({"error": preflight_error}, indent=2))
                return 2
            llm_factory = make_litellm_gateway
        summary = run_experiment_config(
            args.config,
            resume=args.resume,
            output_dir=args.output_dir,
            agent_factories=agent_factories,
            llm_factory=llm_factory,
        )
    except (AgentLoadError, ConfigValidationError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(summary), indent=2))
    return 1 if summary.failed else 0


def _config_llm_models(config_path: str | Path) -> tuple[str, ...] | None:
    config = load_experiment_config(config_path)
    models: list[str] = []
    has_llm_agent = False
    for spec in (config.agents.buyer, config.agents.seller):
        if spec.kind in LLM_AGENT_KINDS:
            has_llm_agent = True
            model = spec.params.get("model")
            if isinstance(model, str) and model:
                models.append(model)
    return tuple(models) if has_llm_agent else None


def _report_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an OpenNegotiation demo HTML report.")
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing one run artifact or multiple run artifact subdirectories.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the HTML report to write.",
    )
    args = parser.parse_args(argv)

    try:
        output_path = write_demo_report(args.input_dir, args.output)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps({"report": str(output_path)}, indent=2))
    return 0


def _strategies_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List OpenNegotiation NPC strategy profiles.")
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
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps(payload, indent=2))
    return 0


def _learn_main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    try:
        output_path = write_battle_report(
            args.input_dir,
            args.output,
            user_role=args.user_role,
            npc_registry_path=args.registry,
            opponent_profile_id=args.opponent_profile,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps({"battle_report": str(output_path)}, indent=2))
    return 0


def _evolve_main(argv: list[str] | None = None) -> int:
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
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps({"strategy_candidate": str(output_path)}, indent=2))
    return 0


def _apply_strategy_main(argv: list[str] | None = None) -> int:
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
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(
        json.dumps(
            {
                "strategy_config": str(output_path),
                "strategy_id": config.strategy_id,
                "version": config.version,
                "role": config.role.value,
            },
            indent=2,
        )
    )
    return 0


def _export_training_adapter_main(argv: list[str] | None = None) -> int:
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
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(
        json.dumps(
            {
                "training_adapter": args.output,
                "adapter_id": package.adapter_id,
                "agent_kind": package.agent_kind,
                "role": package.role.value,
                "strategy_id": package.strategy_id,
                "strategy_version": package.strategy_version,
            },
            indent=2,
        )
    )
    return 0


def _validate_training_adapter_main(argv: list[str] | None = None) -> int:
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
    print(json.dumps(to_jsonable(result), indent=2))
    return 0 if result.status == "passed" else 1


def _compare_main(argv: list[str] | None = None) -> int:
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
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps({"strategy_comparison": str(output_path)}, indent=2))
    return 0


def _leaderboard_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark artifacts into leaderboard JSON."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing benchmark run artifact subdirectories.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write leaderboard_summary.json.",
    )
    args = parser.parse_args(argv)

    try:
        summary = build_leaderboard(args.input_dir)
        if args.output:
            write_leaderboard(args.input_dir, args.output)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(summary), indent=2))
    return 0


def _arena_plan_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a reciprocal arena planning artifact without running it."
    )
    parser.add_argument(
        "--participant",
        action="append",
        dest="participants",
        required=True,
        help="Participant id to include. Provide at least two.",
    )
    parser.add_argument(
        "--scenario-id",
        action="append",
        dest="scenario_ids",
        help="Scenario id to schedule. Defaults to real_market_demo.",
    )
    parser.add_argument(
        "--seed",
        action="append",
        dest="seeds",
        type=int,
        help="Seed to schedule. Defaults to 13.",
    )
    parser.add_argument(
        "--include-self-play",
        action="store_true",
        help="Include diagnostic self-play rows. These should not drive rankings.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write opennego.arena_plan.v1 JSON.",
    )
    args = parser.parse_args(argv)

    try:
        plan = write_arena_plan(
            args.output,
            participants=tuple(args.participants or ()),
            scenario_ids=tuple(args.scenario_ids or ("real_market_demo",)),
            seeds=tuple(args.seeds or (13,)),
            include_self_play=args.include_self_play,
        )
    except (OSError, ArenaPlanError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(plan), indent=2))
    return 0


def _role_swap_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a small no-key role-swapped benchmark track."
    )
    parser.add_argument(
        "--output-dir",
        default="runs/role_swap",
        help="Directory for role-specific runs and combined leaderboard artifacts.",
    )
    parser.add_argument(
        "--config",
        default="configs/real_market_demo.yaml",
        help="Base experiment config whose scenario and transaction settings are reused.",
    )
    parser.add_argument(
        "--participant-id",
        default="baseline_strategy",
        help="Stable strategy identity evaluated as both buyer and seller.",
    )
    args = parser.parse_args(argv)

    try:
        summary = run_role_swap_benchmark(
            output_dir=args.output_dir,
            config_path=args.config,
            participant_id=args.participant_id,
        )
    except (OSError, ValueError, ConfigValidationError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(summary), indent=2))
    return 0 if summary.status == "completed" else 1


def _marketplace_export_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a strategy candidate as a local marketplace profile."
    )
    parser.add_argument(
        "--candidate",
        required=True,
        help="Path to an opennego.strategy_evolution.v1 strategy candidate.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the marketplace profile JSON.",
    )
    parser.add_argument("--profile-id", help="Profile id for the exported strategy.")
    parser.add_argument("--name", help="Human-readable marketplace profile name.")
    parser.add_argument("--summary", help="Short marketplace profile summary.")
    parser.add_argument(
        "--difficulty",
        default="custom",
        help="Marketplace difficulty label for the exported profile.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Additional marketplace tag. Can be provided multiple times.",
    )
    parser.add_argument(
        "--allowed-tool",
        action="append",
        help="Allowed tool name for the profile. Can be provided multiple times.",
    )
    parser.add_argument(
        "--install-registry",
        help="Optional local registry JSON file to append or update.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing installed profile with the same id.",
    )
    args = parser.parse_args(argv)

    try:
        result = write_marketplace_profile(
            args.candidate,
            args.output,
            profile_id=args.profile_id,
            name=args.name,
            summary=args.summary,
            difficulty=args.difficulty,
            tags=tuple(args.tag),
            allowed_tools=tuple(args.allowed_tool) if args.allowed_tool else None,
            install_registry_path=args.install_registry,
            overwrite=args.overwrite,
        )
    except (OSError, StrategyEvolutionError, MarketplaceError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(result), indent=2))
    return 0


def _validate_marketplace_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate local OpenNegotiation strategy marketplace configs."
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_NPC_REGISTRY_PATH),
        help="Strategy registry JSON file to validate.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help=(
            "Standalone opennego.strategy_marketplace_profile.v1 JSON file "
            "to validate. Can be provided multiple times."
        ),
    )
    args = parser.parse_args(argv)

    result = validate_marketplace_configs(
        registry_path=args.registry,
        profile_paths=tuple(args.profile),
    )
    print(json.dumps(to_jsonable(result), indent=2))
    return 0 if result.status == "passed" else 1


def _market_source_policy_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a real-market source policy gate artifact."
    )
    parser.add_argument("--output", required=True, help="Path to write policy JSON.")
    parser.add_argument("--source-id", required=True, help="Source id, e.g. ebay.")
    parser.add_argument(
        "--adapter-kind",
        default="offline_export",
        help="Adapter kind such as offline_export, official_api, or licensed_dataset.",
    )
    parser.add_argument(
        "--collection-mode",
        default="offline_export",
        choices=("fixture", "offline_export", "official_api", "licensed_dataset"),
    )
    parser.add_argument(
        "--data-rights",
        default="user_provided_export",
        help="Declared source/data rights boundary.",
    )
    parser.add_argument("--terms-url", help="Terms/license URL for live-capable sources.")
    parser.add_argument(
        "--privacy-classification",
        default="aggregate_or_user_provided_export",
    )
    parser.add_argument(
        "--allowed-field",
        action="append",
        help="Allowed normalized field. Defaults cover sold-comps fixture fields.",
    )
    parser.add_argument(
        "--prohibited-field",
        action="append",
        help="Prohibited field. Defaults block credentials, raw HTML, and PII.",
    )
    parser.add_argument("--live-collection-enabled", action="store_true")
    args = parser.parse_args(argv)

    try:
        policy = write_market_source_policy(
            args.output,
            source_id=args.source_id,
            adapter_kind=args.adapter_kind,
            collection_mode=args.collection_mode,
            data_rights=args.data_rights,
            terms_url=args.terms_url,
            privacy_classification=args.privacy_classification,
            allowed_fields=tuple(args.allowed_field) if args.allowed_field else None,
            prohibited_fields=(
                tuple(args.prohibited_field) if args.prohibited_field else None
            ),
            live_collection_enabled=args.live_collection_enabled,
        )
    except (OSError, MarketSourcePolicyError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(policy), indent=2))
    return 0


def _validate_market_source_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a real-market source policy artifact."
    )
    parser.add_argument("--policy", required=True, help="Path to source policy JSON.")
    args = parser.parse_args(argv)

    result = validate_market_source_policy(args.policy)
    print(json.dumps(to_jsonable(result), indent=2))
    return 0 if result.status == "passed" else 1


def _ingest_market_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize offline sold-comps CSV/JSON into OpenNegotiation fixtures."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Local CSV or JSON-list sold-comps export.",
    )
    parser.add_argument(
        "--products-output",
        required=True,
        help="Path to write normalized products.json.",
    )
    parser.add_argument(
        "--comps-output",
        required=True,
        help="Path to write normalized market_comps.json.",
    )
    parser.add_argument(
        "--manifest-output",
        help=(
            "Optional path to write a versioned aggregate dataset manifest "
            "with provenance and quality stats."
        ),
    )
    parser.add_argument(
        "--source",
        default="offline_sold_comps",
        help="Fallback source label when input rows do not include one.",
    )
    parser.add_argument(
        "--currency",
        default="USD",
        help="Fallback currency when input rows do not include one.",
    )
    parser.add_argument("--window-days", type=int)
    parser.add_argument("--asking-multiplier", type=float, default=1.25)
    parser.add_argument("--buyer-budget-multiplier", type=float, default=1.2)
    parser.add_argument(
        "--source-policy",
        help=(
            "Optional opennego.market_source_policy.v1 artifact to validate and "
            "attach to the dataset manifest."
        ),
    )
    args = parser.parse_args(argv)

    try:
        result = ingest_market_data(
            input_path=args.input,
            products_output=args.products_output,
            comps_output=args.comps_output,
            source=args.source,
            currency=args.currency,
            window_days=args.window_days,
            asking_multiplier=args.asking_multiplier,
            buyer_budget_multiplier=args.buyer_budget_multiplier,
            manifest_output=args.manifest_output,
            source_policy_path=args.source_policy,
        )
    except (OSError, MarketIngestionError, MarketSourcePolicyError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(result), indent=2))
    return 0


def _ingest_ebay_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch eBay Marketplace Insights sold-comps data and normalize it "
            "into OpenNegotiation fixtures."
        )
    )
    parser.add_argument("--query", required=True, help="Sold-comps search query.")
    parser.add_argument(
        "--source-policy",
        required=True,
        help=(
            "Validated live opennego.market_source_policy.v1 artifact. Must use "
            "collection_mode=official_api and live_collection_enabled=true."
        ),
    )
    parser.add_argument(
        "--snapshot-output",
        required=True,
        help="Path to write the sanitized eBay sold-comps snapshot JSON.",
    )
    parser.add_argument(
        "--products-output",
        required=True,
        help="Path to write normalized products.json.",
    )
    parser.add_argument(
        "--comps-output",
        required=True,
        help="Path to write normalized market_comps.json.",
    )
    parser.add_argument(
        "--manifest-output",
        help="Optional path to write the aggregate market dataset manifest.",
    )
    parser.add_argument(
        "--marketplace-id",
        default="EBAY_US",
        help="eBay marketplace header, e.g. EBAY_US or EBAY_GB.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum sold-comps records to ingest.",
    )
    parser.add_argument(
        "--category-id",
        action="append",
        help="Optional eBay category id. Can be provided multiple times.",
    )
    parser.add_argument(
        "--filter",
        dest="item_filter",
        action="append",
        help="Optional Marketplace Insights filter expression.",
    )
    parser.add_argument(
        "--environment",
        default="production",
        choices=("production", "sandbox"),
        help="eBay API environment.",
    )
    parser.add_argument(
        "--mock-response",
        help=(
            "Contract-test path to a saved Marketplace Insights JSON response. "
            "Skips OAuth and network calls."
        ),
    )
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--asking-multiplier", type=float, default=1.25)
    parser.add_argument("--buyer-budget-multiplier", type=float, default=1.2)
    args = parser.parse_args(argv)

    try:
        ebay_adapter = importlib.import_module(
            "opennego.adapters.ebay_marketplace_insights"
        )
        result = ebay_adapter.ingest_ebay_marketplace_insights(
            query=args.query,
            source_policy_path=args.source_policy,
            snapshot_output=args.snapshot_output,
            products_output=args.products_output,
            comps_output=args.comps_output,
            manifest_output=args.manifest_output,
            marketplace_id=args.marketplace_id,
            limit=args.limit,
            category_ids=tuple(args.category_id or ()),
            item_filter=tuple(args.item_filter or ()),
            environment=args.environment,
            mock_response_path=args.mock_response,
            currency=args.currency,
            window_days=args.window_days,
            asking_multiplier=args.asking_multiplier,
            buyer_budget_multiplier=args.buyer_budget_multiplier,
        )
    except (OSError, RuntimeError, MarketSourcePolicyError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(result), indent=2))
    return 0


def _validate_market_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate normalized OpenNegotiation market fixture files."
    )
    parser.add_argument(
        "--products-file",
        required=True,
        help="Path to normalized products.json.",
    )
    parser.add_argument(
        "--market-comps-file",
        required=True,
        help="Path to normalized market_comps.json.",
    )
    parser.add_argument(
        "--manifest-file",
        help="Optional market dataset manifest produced by ingest-market.",
    )
    args = parser.parse_args(argv)

    result = validate_market_dataset(
        products_file=args.products_file,
        market_comps_file=args.market_comps_file,
        manifest_file=args.manifest_file,
    )
    print(json.dumps(to_jsonable(result), indent=2))
    return 0 if result.status == "passed" else 1


def _validate_demo_bundle_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an OpenNegotiation demo bundle manifest."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to demo_manifest.json produced by opennego demo.",
    )
    args = parser.parse_args(argv)

    result = validate_demo_bundle(args.manifest)
    print(json.dumps(to_jsonable(result), indent=2))
    return 0 if result.status == "passed" else 1


def _demo_main(argv: list[str] | None = None, *, legacy: bool = False) -> int:
    output_default = "runs/mvp_demo" if legacy else "runs/demo"
    report_default = "opennego_mvp_demo.html" if legacy else "opennegotiation_demo.html"
    parser = argparse.ArgumentParser(
        description="Generate the local OpenNegotiation demo end to end."
    )
    parser.add_argument(
        "--output-dir",
        default=output_default,
        help="Directory for benchmark artifacts and battle_report.json.",
    )
    parser.add_argument(
        "--report",
        help=f"Optional HTML report path. Defaults to <output-dir>/{report_default}.",
    )
    parser.add_argument(
        "--config",
        default="configs/real_market_demo.yaml",
        help="Experiment config used for the benchmark slice.",
    )
    parser.add_argument(
        "--learning-tool-regime",
        default="no_tools",
        help="Completed run tool regime to diagnose for policy learning.",
    )
    parser.add_argument(
        "--user-role",
        default="buyer",
        choices=("buyer", "seller"),
        help="Role of the user-owned agent to optimize.",
    )
    parser.add_argument(
        "--opponent-profile",
        default="seller_hardline_anchor_v1",
        help="NPC strategy profile id for the counterparty.",
    )
    args = parser.parse_args(argv)

    try:
        runner = run_mvp_demo if legacy else run_demo
        summary = runner(
            output_dir=args.output_dir,
            report_path=args.report,
            config_path=args.config,
            learning_tool_regime=args.learning_tool_regime,
            user_role=args.user_role,
            opponent_profile_id=args.opponent_profile,
        )
    except (OSError, ValueError, KeyError, ConfigValidationError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(summary), indent=2))
    return 0 if summary.benchmark_failed == 0 else 1


def _handoff_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a validated no-key external handoff package."
    )
    parser.add_argument(
        "--output-dir",
        default="runs/external_handoff",
        help="Directory for the handoff package.",
    )
    parser.add_argument(
        "--config",
        default="configs/real_market_demo.yaml",
        help="Fixture config reused for demo and role-swapped runs.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_NPC_REGISTRY_PATH),
        help="Path to the local NPC strategy registry to validate.",
    )
    parser.add_argument(
        "--products-file",
        default="examples/data/real_market_products.json",
        help="Products fixture file to validate for handoff.",
    )
    parser.add_argument(
        "--market-comps-file",
        default="examples/data/real_market_comps.json",
        help="Market comparables fixture file to validate for handoff.",
    )
    parser.add_argument(
        "--participant-id",
        default="baseline_strategy",
        help="Stable participant id used for the role-swapped handoff track.",
    )
    args = parser.parse_args(argv)

    try:
        summary = run_external_handoff_package(
            output_dir=args.output_dir,
            config_path=args.config,
            registry_path=args.registry,
            products_file=args.products_file,
            market_comps_file=args.market_comps_file,
            participant_id=args.participant_id,
        )
    except (OSError, ValueError, KeyError, ConfigValidationError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(summary), indent=2))
    return 0 if summary.status == "passed" else 1


def _train_main(argv: list[str] | None = None) -> int:
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
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(summary), indent=2))
    return 0 if summary.status == "completed" else 1


def _spar_main(argv: list[str] | None = None) -> int:
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
            preflight_error = _run_models_preflight_error((args.user_llm_model,))
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
            preflight_error = _run_models_preflight_error((args.opponent_llm_model,))
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
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    payload = dict(to_jsonable(summary))
    if html_report is not None:
        payload["html_report"] = str(html_report)
    print(json.dumps(payload, indent=2))
    return 0 if summary.failed == 0 else 1


def _profile_litellm_opponent_factory(
    *,
    model: str,
    tool_policy: str,
    temperature: float,
    max_tokens: int | None,
):
    llm = make_litellm_gateway()

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
    llm = make_litellm_gateway()
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


def _run_models_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a tiny live-model OpenNegotiation demo.")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODEL_DEMO_MODELS),
        help="Comma-separated LiteLLM model ids.",
    )
    parser.add_argument(
        "--output-dir",
        default="runs/five_model_demo",
        help="Directory for model run artifacts.",
    )
    parser.add_argument(
        "--products-file",
        default="examples/data/real_market_products.json",
    )
    parser.add_argument(
        "--market-comps-file",
        default="examples/data/real_market_comps.json",
    )
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=384)
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args(argv)

    models = tuple(model.strip() for model in args.models.split(",") if model.strip())
    if not models:
        print(json.dumps({"error": "--models must include at least one model"}, indent=2))
        return 2
    preflight_error = _run_models_preflight_error(models)
    if preflight_error is not None:
        print(json.dumps({"error": preflight_error}, indent=2))
        return 2

    summary = run_model_demo(
        models=models,
        output_dir=args.output_dir,
        products_file=args.products_file,
        market_comps_file=args.market_comps_file,
        max_turns=args.max_turns,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        fail_fast=args.fail_fast,
    )
    print(json.dumps(to_jsonable(summary), indent=2))
    return 1 if summary.failed else 0


def _run_models_preflight_error(models: tuple[str, ...]) -> str | None:
    if importlib.util.find_spec("litellm") is None:
        return (
            "LiteLLM is not installed. Install optional dependencies with: "
            "python -m pip install -e '.[llm]'"
        )

    missing = []
    if any(model.startswith("openrouter/") for model in models):
        if not os.environ.get("OPENROUTER_API_KEY"):
            missing.append("OPENROUTER_API_KEY")
    if any(model.startswith("openai/") for model in models):
        if not os.environ.get("OPENAI_API_KEY"):
            missing.append("OPENAI_API_KEY")
    if any(model.startswith("anthropic/") for model in models):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            missing.append("ANTHROPIC_API_KEY")

    if missing:
        return "Missing provider environment variable(s): " + ", ".join(sorted(set(missing)))
    return None


if __name__ == "__main__":
    raise SystemExit(main())
