"""Scenario pack commands: build and validate runnable scenario libraries."""

from __future__ import annotations

import argparse

from opennego.artifacts import to_jsonable
from opennego.scenario_pack import (
    ScenarioPackError,
    build_scenario_pack,
    validate_scenario_pack,
)

from . import common


def scenarios_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opennego scenarios",
        description="Build and validate scenario packs from validated market data.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    build = subparsers.add_parser(
        "build",
        help="Generate a runnable scenario pack with BATNA-derived constraints.",
    )
    build.add_argument(
        "--products-file",
        required=True,
        help="Normalized products.json with market_reference statistics.",
    )
    build.add_argument(
        "--market-comps-file",
        required=True,
        help="Normalized market_comps.json used for tool-backed regimes.",
    )
    build.add_argument(
        "--dataset-manifest",
        help="Optional market dataset manifest produced by ingest-market.",
    )
    build.add_argument(
        "--output-dir",
        required=True,
        help="Directory for scenarios.json, experiment_config.json, and pack_manifest.json.",
    )
    build.add_argument("--seed", type=int, default=13)
    build.add_argument("--scenarios-per-product", type=int, default=1)
    build.add_argument("--max-turns", type=int, default=8)
    build.add_argument("--name", help="Pack name. Defaults to scenario_pack_s<seed>.")

    validate = subparsers.add_parser(
        "validate",
        help="Validate a pack manifest, artifacts, and source fingerprints.",
    )
    validate.add_argument(
        "--manifest",
        required=True,
        help="Path to pack_manifest.json produced by scenarios build.",
    )

    args = parser.parse_args(argv)

    if args.subcommand == "build":
        try:
            summary = build_scenario_pack(
                products_file=args.products_file,
                market_comps_file=args.market_comps_file,
                dataset_manifest_file=args.dataset_manifest,
                output_dir=args.output_dir,
                seed=args.seed,
                scenarios_per_product=args.scenarios_per_product,
                max_turns=args.max_turns,
                name=args.name,
            )
        except (OSError, ScenarioPackError, ValueError) as exc:
            return common.print_error(exc)
        common.print_json(to_jsonable(summary))
        return 0

    result = validate_scenario_pack(args.manifest)
    common.print_json(to_jsonable(result))
    return 0 if result.status == "passed" else 1
