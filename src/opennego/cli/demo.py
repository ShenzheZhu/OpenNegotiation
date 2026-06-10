"""Demo commands: one-command local demo, bundle validation, live model demo."""

from __future__ import annotations

import argparse

from opennego.artifacts import to_jsonable
from opennego.demo import run_demo, validate_demo_bundle
from opennego.model_demo import DEFAULT_MODEL_DEMO_MODELS, run_model_demo
from opennego.runner import ConfigValidationError

from . import common


def demo_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the local OpenNegotiation demo end to end."
    )
    parser.add_argument(
        "--output-dir",
        default="runs/demo",
        help="Directory for benchmark artifacts and battle_report.json.",
    )
    parser.add_argument(
        "--report",
        help="Optional HTML report path. Defaults to <output-dir>/opennegotiation_demo.html.",
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
        summary = run_demo(
            output_dir=args.output_dir,
            report_path=args.report,
            config_path=args.config,
            learning_tool_regime=args.learning_tool_regime,
            user_role=args.user_role,
            opponent_profile_id=args.opponent_profile,
        )
    except (OSError, ValueError, KeyError, ConfigValidationError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(summary))
    return 0 if summary.benchmark_failed == 0 else 1


def validate_demo_main(argv: list[str] | None = None) -> int:
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
    common.print_json(to_jsonable(result))
    return 0 if result.status == "passed" else 1


def run_models_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a tiny live-model OpenNegotiation demo."
    )
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
        return common.print_error("--models must include at least one model")
    preflight_error = common.llm_preflight_error(models)
    if preflight_error is not None:
        return common.print_error(preflight_error)

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
    common.print_json(to_jsonable(summary))
    return 1 if summary.failed else 0
