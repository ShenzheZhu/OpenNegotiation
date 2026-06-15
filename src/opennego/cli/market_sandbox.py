"""Market sandbox commands: run a concurrent market episode."""

from __future__ import annotations

import argparse

from opennego.artifacts import to_jsonable
from opennego.market import MarketError, build_market, step_market
from opennego.market_runtime import MarketRuntimeError, run_market_episode

from . import common


def market_calibrate_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opennego market-calibrate",
        description="Compare a market episode's distributions to a reference.",
    )
    parser.add_argument(
        "--products-file",
        default="examples/data/scenario_seed_products.json",
        help="Products fixture used to build the listings pool.",
    )
    parser.add_argument(
        "--reference",
        default="examples/data/market_calibration_reference.json",
        help="Reference distribution JSON (real-market or fixture).",
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
    parser.add_argument("--tolerance", type=float, default=0.20)
    parser.add_argument("--output", help="Optional path for the calibration report.")
    args = parser.parse_args(argv)

    from opennego.market_calibration import (
        CalibrationError,
        calibrate_episode,
        load_reference,
    )

    buyers = args.buyers or ["buyer_a", "buyer_b", "buyer_c"]
    try:
        state = build_market(args.products_file, seed=args.seed)
        episode = run_market_episode(
            state,
            buyer_ids=buyers,
            shortlist_size=args.shortlist_size,
            max_turns=args.max_turns,
            seed=args.seed,
        )
        reference = load_reference(args.reference)
        report = calibrate_episode(
            episode,
            reference=reference,
            tolerance=args.tolerance,
            output_path=args.output,
        )
    except (OSError, MarketError, MarketRuntimeError, CalibrationError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(report))
    return 0 if report.status in {"calibrated", "no_data"} else 1


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
        "--level",
        choices=("L1", "L2", "L3"),
        help=(
            "Run a single buyer at a staged autonomy level (L1 assigned, "
            "L2 shortlist-select, L3 free concurrent) instead of a full episode."
        ),
    )
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
            if args.level:
                from opennego.market_autonomy import run_autonomy_episode

                result = run_autonomy_episode(
                    state,
                    buyer_id=buyers[0],
                    level=args.level,
                    shortlist_size=args.shortlist_size,
                    max_turns=args.max_turns,
                    seed=args.seed,
                    store=store,
                    output_path=args.output,
                )
            else:
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
