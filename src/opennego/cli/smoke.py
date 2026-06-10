"""Deterministic no-key smoke negotiation run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import to_jsonable, write_run_artifacts
from opennego.environment import NegotiationEnvironment
from opennego.schema import Scenario
from opennego.tools import MarketPriceTool

from . import common


def smoke_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opennego",
        description="Run a deterministic OpenNegotiation smoke demo.",
    )
    parser.add_argument("--products-file", default="examples/data/products.json")
    parser.add_argument("--market-comps-file", default="examples/data/market_comps.json")
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--output-json", help="Optional path for the full run trace.")
    parser.add_argument("--output-dir", help="Optional directory for versioned benchmark artifacts.")
    parser.add_argument("--run-id", help="Run id for benchmark artifacts.")
    parser.add_argument("--seed", type=int, help="Seed recorded in benchmark artifacts.")
    args = parser.parse_args(argv)

    product = common.load_first_product(args.products_file)
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

    common.print_json(
        {
            "outcome": result.outcome,
            "deal_price": result.deal_price,
            "completed_turns": result.completed_turns,
            "metrics": result.metrics,
            "artifacts": str(paths.output_dir) if paths else None,
        }
    )
    return 0
