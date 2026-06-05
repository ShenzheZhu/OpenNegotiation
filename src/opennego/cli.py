"""Command-line smoke runner for OpenNego."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.environment import NegotiationEnvironment
from opennego.schema import Product, Scenario
from opennego.tools import MarketPriceTool


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


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
    payload = _jsonable(result)

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, indent=2) + "\n")

    print(
        json.dumps(
            {
                "outcome": result.outcome,
                "deal_price": result.deal_price,
                "completed_turns": result.completed_turns,
                "metrics": result.metrics,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
