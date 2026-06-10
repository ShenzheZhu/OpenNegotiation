"""Market data commands: source policies, ingestion, and fixture validation."""

from __future__ import annotations

import argparse
import importlib

from opennego.artifacts import to_jsonable
from opennego.market_ingestion import MarketIngestionError, ingest_market_data
from opennego.market_sources import (
    MarketSourcePolicyError,
    validate_market_source_policy,
    write_market_source_policy,
)
from opennego.market_validation import validate_market_dataset

from . import common


def market_source_policy_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a real-market source policy gate artifact."
    )
    parser.add_argument("--output", required=True, help="Path to write policy JSON.")
    parser.add_argument("--source-id", required=True, help="Source id, e.g. ebay.")
    parser.add_argument(
        "--adapter-kind",
        default="offline_export",
        help="Adapter kind such as offline_export, official_api, or licensed_dataset.",
    )
    parser.add_argument(
        "--collection-mode",
        default="offline_export",
        choices=("fixture", "offline_export", "official_api", "licensed_dataset"),
    )
    parser.add_argument(
        "--data-rights",
        default="user_provided_export",
        help="Declared source/data rights boundary.",
    )
    parser.add_argument("--terms-url", help="Terms/license URL for live-capable sources.")
    parser.add_argument(
        "--privacy-classification",
        default="aggregate_or_user_provided_export",
    )
    parser.add_argument(
        "--allowed-field",
        action="append",
        help="Allowed normalized field. Defaults cover sold-comps fixture fields.",
    )
    parser.add_argument(
        "--prohibited-field",
        action="append",
        help="Prohibited field. Defaults block credentials, raw HTML, and PII.",
    )
    parser.add_argument("--live-collection-enabled", action="store_true")
    args = parser.parse_args(argv)

    try:
        policy = write_market_source_policy(
            args.output,
            source_id=args.source_id,
            adapter_kind=args.adapter_kind,
            collection_mode=args.collection_mode,
            data_rights=args.data_rights,
            terms_url=args.terms_url,
            privacy_classification=args.privacy_classification,
            allowed_fields=tuple(args.allowed_field) if args.allowed_field else None,
            prohibited_fields=(
                tuple(args.prohibited_field) if args.prohibited_field else None
            ),
            live_collection_enabled=args.live_collection_enabled,
        )
    except (OSError, MarketSourcePolicyError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(policy))
    return 0


def validate_market_source_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a real-market source policy artifact."
    )
    parser.add_argument("--policy", required=True, help="Path to source policy JSON.")
    args = parser.parse_args(argv)

    result = validate_market_source_policy(args.policy)
    common.print_json(to_jsonable(result))
    return 0 if result.status == "passed" else 1


def ingest_market_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize offline sold-comps CSV/JSON into OpenNegotiation fixtures."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Local CSV or JSON-list sold-comps export.",
    )
    parser.add_argument(
        "--products-output",
        required=True,
        help="Path to write normalized products.json.",
    )
    parser.add_argument(
        "--comps-output",
        required=True,
        help="Path to write normalized market_comps.json.",
    )
    parser.add_argument(
        "--manifest-output",
        help=(
            "Optional path to write a versioned aggregate dataset manifest "
            "with provenance and quality stats."
        ),
    )
    parser.add_argument(
        "--source",
        default="offline_sold_comps",
        help="Fallback source label when input rows do not include one.",
    )
    parser.add_argument(
        "--currency",
        default="USD",
        help="Fallback currency when input rows do not include one.",
    )
    parser.add_argument("--window-days", type=int)
    parser.add_argument("--asking-multiplier", type=float, default=1.25)
    parser.add_argument("--buyer-budget-multiplier", type=float, default=1.2)
    parser.add_argument(
        "--source-policy",
        help=(
            "Optional opennego.market_source_policy.v1 artifact to validate and "
            "attach to the dataset manifest."
        ),
    )
    args = parser.parse_args(argv)

    try:
        result = ingest_market_data(
            input_path=args.input,
            products_output=args.products_output,
            comps_output=args.comps_output,
            source=args.source,
            currency=args.currency,
            window_days=args.window_days,
            asking_multiplier=args.asking_multiplier,
            buyer_budget_multiplier=args.buyer_budget_multiplier,
            manifest_output=args.manifest_output,
            source_policy_path=args.source_policy,
        )
    except (OSError, MarketIngestionError, MarketSourcePolicyError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(result))
    return 0


def ingest_ebay_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch eBay Marketplace Insights sold-comps data and normalize it "
            "into OpenNegotiation fixtures."
        )
    )
    parser.add_argument("--query", required=True, help="Sold-comps search query.")
    parser.add_argument(
        "--source-policy",
        required=True,
        help=(
            "Validated live opennego.market_source_policy.v1 artifact. Must use "
            "collection_mode=official_api and live_collection_enabled=true."
        ),
    )
    parser.add_argument(
        "--snapshot-output",
        required=True,
        help="Path to write the sanitized eBay sold-comps snapshot JSON.",
    )
    parser.add_argument(
        "--products-output",
        required=True,
        help="Path to write normalized products.json.",
    )
    parser.add_argument(
        "--comps-output",
        required=True,
        help="Path to write normalized market_comps.json.",
    )
    parser.add_argument(
        "--manifest-output",
        help="Optional path to write the aggregate market dataset manifest.",
    )
    parser.add_argument(
        "--marketplace-id",
        default="EBAY_US",
        help="eBay marketplace header, e.g. EBAY_US or EBAY_GB.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum sold-comps records to ingest.",
    )
    parser.add_argument(
        "--category-id",
        action="append",
        help="Optional eBay category id. Can be provided multiple times.",
    )
    parser.add_argument(
        "--filter",
        dest="item_filter",
        action="append",
        help="Optional Marketplace Insights filter expression.",
    )
    parser.add_argument(
        "--environment",
        default="production",
        choices=("production", "sandbox"),
        help="eBay API environment.",
    )
    parser.add_argument(
        "--mock-response",
        help=(
            "Contract-test path to a saved Marketplace Insights JSON response. "
            "Skips OAuth and network calls."
        ),
    )
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--asking-multiplier", type=float, default=1.25)
    parser.add_argument("--buyer-budget-multiplier", type=float, default=1.2)
    args = parser.parse_args(argv)

    try:
        ebay_adapter = importlib.import_module(
            "opennego.adapters.ebay_marketplace_insights"
        )
        result = ebay_adapter.ingest_ebay_marketplace_insights(
            query=args.query,
            source_policy_path=args.source_policy,
            snapshot_output=args.snapshot_output,
            products_output=args.products_output,
            comps_output=args.comps_output,
            manifest_output=args.manifest_output,
            marketplace_id=args.marketplace_id,
            limit=args.limit,
            category_ids=tuple(args.category_id or ()),
            item_filter=tuple(args.item_filter or ()),
            environment=args.environment,
            mock_response_path=args.mock_response,
            currency=args.currency,
            window_days=args.window_days,
            asking_multiplier=args.asking_multiplier,
            buyer_budget_multiplier=args.buyer_budget_multiplier,
        )
    except (OSError, RuntimeError, MarketSourcePolicyError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(result))
    return 0


def validate_market_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate normalized OpenNegotiation market fixture files."
    )
    parser.add_argument(
        "--products-file",
        required=True,
        help="Path to normalized products.json.",
    )
    parser.add_argument(
        "--market-comps-file",
        required=True,
        help="Path to normalized market_comps.json.",
    )
    parser.add_argument(
        "--manifest-file",
        help="Optional market dataset manifest produced by ingest-market.",
    )
    args = parser.parse_args(argv)

    result = validate_market_dataset(
        products_file=args.products_file,
        market_comps_file=args.market_comps_file,
        manifest_file=args.manifest_file,
    )
    common.print_json(to_jsonable(result))
    return 0 if result.status == "passed" else 1
