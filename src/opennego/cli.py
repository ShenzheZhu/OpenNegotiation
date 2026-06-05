"""Command-line entry points for OpenNego."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from opennego.artifacts import to_jsonable, write_run_artifacts
from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.environment import NegotiationEnvironment
from opennego.report import write_demo_report
from opennego.runner import ConfigValidationError, run_experiment_config
from opennego.schema import Product, Scenario
from opennego.tools import MarketPriceTool


def load_first_product(path: str | Path) -> Product:
    records = json.loads(Path(path).read_text())
    if not records:
        raise ValueError(f"No products found in {path}")
    return Product.from_mapping(records[0])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "run":
        return _run_config_main(argv[1:])
    if argv and argv[0] == "report":
        return _report_main(argv[1:])

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
    args = parser.parse_args(argv)

    try:
        summary = run_experiment_config(
            args.config,
            resume=args.resume,
            output_dir=args.output_dir,
        )
    except ConfigValidationError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(to_jsonable(summary), indent=2))
    return 1 if summary.failed else 0


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


if __name__ == "__main__":
    raise SystemExit(main())
