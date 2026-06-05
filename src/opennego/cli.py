"""Command-line entry points for OpenNego."""

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
from opennego.artifacts import to_jsonable, write_run_artifacts
from opennego.agents import ScriptedSeller, ToolAwareBuyer, make_profile_llm_agent
from opennego.environment import NegotiationEnvironment
from opennego.evolution import (
    StrategyEvolutionError,
    write_strategy_candidate,
    write_strategy_comparison,
)
from opennego.learning import (
    DEFAULT_NPC_REGISTRY_PATH,
    registry_listing,
    write_battle_report,
)
from opennego.leaderboard import build_leaderboard, write_leaderboard
from opennego.market_ingestion import MarketIngestionError, ingest_market_data
from opennego.market_validation import validate_market_dataset
from opennego.marketplace import MarketplaceError, write_marketplace_profile
from opennego.model_demo import (
    DEFAULT_MODEL_DEMO_MODELS,
    make_litellm_gateway,
    run_model_demo,
)
from opennego.mvp_demo import run_mvp_demo, validate_mvp_demo_bundle
from opennego.report import write_demo_report
from opennego.runner import (
    ConfigValidationError,
    LLM_AGENT_KINDS,
    load_experiment_config,
    run_experiment_config,
)
from opennego.schema import Product, Scenario
from opennego.sparring import run_sparring_suite
from opennego.sparring_report import write_sparring_report
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
    if argv and argv[0] == "compare":
        return _compare_main(argv[1:])
    if argv and argv[0] == "leaderboard":
        return _leaderboard_main(argv[1:])
    if argv and argv[0] == "marketplace-export":
        return _marketplace_export_main(argv[1:])
    if argv and argv[0] == "ingest-market":
        return _ingest_market_main(argv[1:])
    if argv and argv[0] == "validate-market":
        return _validate_market_main(argv[1:])
    if argv and argv[0] == "validate-demo-bundle":
        return _validate_demo_bundle_main(argv[1:])
    if argv and argv[0] == "mvp-demo":
        return _mvp_demo_main(argv[1:])
    if argv and argv[0] == "train":
        return _train_main(argv[1:])
    if argv and argv[0] == "spar":
        return _spar_main(argv[1:])

    parser = argparse.ArgumentParser(description="Run a deterministic OpenNego smoke demo.")
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
    parser = argparse.ArgumentParser(description="Run an OpenNego experiment config.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an OpenNego experiment config.",
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
    parser = argparse.ArgumentParser(description="Generate an OpenNego demo HTML report.")
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
    parser = argparse.ArgumentParser(description="List OpenNego NPC strategy profiles.")
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


def _ingest_market_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize offline sold-comps CSV/JSON into OpenNego fixtures."
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
        )
    except (OSError, MarketIngestionError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(result), indent=2))
    return 0


def _validate_market_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate normalized OpenNego market fixture files."
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
        description="Validate an OpenNego MVP demo bundle manifest."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to mvp_demo_manifest.json produced by opennego mvp-demo.",
    )
    args = parser.parse_args(argv)

    result = validate_mvp_demo_bundle(args.manifest)
    print(json.dumps(to_jsonable(result), indent=2))
    return 0 if result.status == "passed" else 1


def _mvp_demo_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the no-key OpenNego MVP demo end to end."
    )
    parser.add_argument(
        "--output-dir",
        default="runs/mvp_demo",
        help="Directory for benchmark artifacts and battle_report.json.",
    )
    parser.add_argument(
        "--report",
        help="Optional HTML report path. Defaults to <output-dir>/opennego_mvp_demo.html.",
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
        summary = run_mvp_demo(
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
            "Load a local (role, params) AgentPort factory for the user agent. "
            "Cannot be combined with --user-strategy."
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
        if args.user_agent_factory:
            user_agent_factory = load_sparring_user_agent_factory(
                args.user_agent_factory,
                params=parse_agent_params(args.user_agent_param),
            )
            user_agent_kind = args.user_agent_kind or "module_user_agent"
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


def _run_models_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a tiny live-model OpenNego demo.")
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
