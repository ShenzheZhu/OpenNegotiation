"""Skill drill commands: controlled, scored market-skill exercises."""

from __future__ import annotations

import argparse

from opennego.artifacts import to_jsonable
from opennego.skill_drills import (
    SkillDrillError,
    run_selection_drill,
    run_walkaway_drill,
)

from . import common


def drill_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opennego drill",
        description="Run a controlled market-skill drill.",
    )
    subparsers = parser.add_subparsers(dest="skill", required=True)

    select = subparsers.add_parser(
        "select", help="Listing-selection drill: pick the most attainable deal."
    )
    select.add_argument("--seed", type=int, default=13)
    select.add_argument("--count", type=int, default=5)
    select.add_argument("--market-reference", type=float, default=575.0)
    select.add_argument(
        "--policy",
        default="risk_aware",
        choices=("risk_aware", "lowest_asking"),
        help="Built-in selection policy to score.",
    )
    select.add_argument("--output", help="Optional path for the drill artifact.")

    walkaway = subparsers.add_parser(
        "walkaway", help="Walk-away drill: cut losses fast, but not on a real deal."
    )
    walkaway.add_argument("--seed", type=int, default=13)
    walkaway.add_argument("--market-reference", type=float, default=575.0)
    walkaway.add_argument("--max-turns", type=int, default=10)
    walkaway.add_argument(
        "--patience",
        type=int,
        default=2,
        help="Non-conceding seller offers tolerated before walking.",
    )
    walkaway.add_argument("--output", help="Optional path for the drill artifact.")

    args = parser.parse_args(argv)

    try:
        if args.skill == "select":
            result = run_selection_drill(
                seed=args.seed,
                count=args.count,
                market_reference=args.market_reference,
                policy=args.policy,
                output_path=args.output,
            )
        elif args.skill == "walkaway":
            result = run_walkaway_drill(
                seed=args.seed,
                patience=args.patience,
                market_reference=args.market_reference,
                max_turns=args.max_turns,
                output_path=args.output,
            )
        else:
            return common.print_error(f"unknown drill: {args.skill}")
    except (OSError, SkillDrillError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(result))
    return 0
