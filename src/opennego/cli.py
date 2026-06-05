"""Command-line smoke runner for OpenNego."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from opennego.artifacts import to_jsonable, write_run_artifacts
from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.environment import NegotiationEnvironment
from opennego.schema import Product, Scenario
from opennego.tools import MarketPriceTool


def load_first_product(path: str | Path) -> Product:
    records = json.loads(Path(path).read_text())
    if not records:
        raise ValueError(f"No products found in {path}")
    return Product.from_mapping(records[0])


def main(argv: list[str] | None = None) -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
