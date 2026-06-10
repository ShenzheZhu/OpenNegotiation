"""Strategy marketplace commands: profile export and registry validation."""

from __future__ import annotations

import argparse

from opennego.artifacts import to_jsonable
from opennego.evolution import StrategyEvolutionError
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH
from opennego.marketplace import (
    MarketplaceError,
    validate_marketplace_configs,
    write_marketplace_profile,
)

from . import common


def marketplace_export_main(argv: list[str] | None = None) -> int:
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
        return common.print_error(exc)

    common.print_json(to_jsonable(result))
    return 0


def validate_marketplace_main(argv: list[str] | None = None) -> int:
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
    common.print_json(to_jsonable(result))
    return 0 if result.status == "passed" else 1
