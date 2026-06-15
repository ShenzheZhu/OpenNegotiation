"""Market sandbox commands: run a concurrent market episode."""

from __future__ import annotations

import argparse

from opennego.artifacts import to_jsonable
from opennego.market import MarketError, build_market, step_market
from opennego.market_runtime import MarketRuntimeError, run_market_episode

from . import common


def market_run_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opennego market-run",
        description="Run a concurrent market episode over a listings pool.",
    )
    parser.add_argument(
        "--products-file",
        default="examples/data/scenario_seed_products.json",
        help="Products fixture used to build the listings pool.",
    )
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument(
        "--buyer",
        action="append",
        dest="buyers",
        help="Buyer participant id. Repeat for multiple buyers.",
    )
    parser.add_argument("--shortlist-size", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument(
        "--warm-periods",
        type=int,
        default=0,
        help="Advance the market lifecycle this many periods before running.",
    )
    parser.add_argument(
        "--store",
        help="Optional rating store path to ingest the episode scores into.",
    )
    parser.add_argument("--output", help="Optional path for the episode artifact.")
    args = parser.parse_args(argv)

    buyers = args.buyers or ["buyer_a", "buyer_b"]
    try:
        state = build_market(args.products_file, seed=args.seed)
        for _ in range(max(0, args.warm_periods)):
            state = step_market(state)
        store = None
        if args.store:
            from opennego.rating import RatingStore

            store = RatingStore(args.store)
        try:
            result = run_market_episode(
                state,
                buyer_ids=buyers,
                shortlist_size=args.shortlist_size,
                max_turns=args.max_turns,
                seed=args.seed,
                store=store,
                output_path=args.output,
            )
        finally:
            if store is not None:
                store.close()
    except (OSError, MarketError, MarketRuntimeError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(result))
    return 0
