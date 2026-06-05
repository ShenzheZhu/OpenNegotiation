"""Validation helpers for offline market fixture datasets."""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.market_ingestion import MARKET_DATASET_MANIFEST_SCHEMA_VERSION
from opennego.schema import Product
from opennego.tools import MarketComparable

MARKET_VALIDATION_SCHEMA_VERSION = "opennego.market_validation.v1"


@dataclass(frozen=True)
class MarketValidationResult:
    schema_version: str
    status: str
    products_file: str
    market_comps_file: str
    manifest_file: str | None
    product_count: int
    comparable_count: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_market_dataset(
    *,
    products_file: str | Path,
    market_comps_file: str | Path,
    manifest_file: str | Path | None = None,
) -> MarketValidationResult:
    """Validate normalized market fixtures and an optional dataset manifest."""

    products_path = Path(products_file)
    comps_path = Path(market_comps_file)
    manifest_path = Path(manifest_file) if manifest_file is not None else None
    errors: list[str] = []
    warnings: list[str] = []

    products = _load_products(products_path, errors)
    comparables = _load_comparables(comps_path, errors)
    _validate_fixture_coverage(products, comparables, warnings)
    if manifest_path is not None:
        _validate_manifest(
            manifest_path=manifest_path,
            products_path=products_path,
            comps_path=comps_path,
            product_count=len(products),
            comparables=comparables,
            errors=errors,
            warnings=warnings,
        )

    status = "passed" if not errors else "failed"
    return MarketValidationResult(
        schema_version=MARKET_VALIDATION_SCHEMA_VERSION,
        status=status,
        products_file=str(products_path),
        market_comps_file=str(comps_path),
        manifest_file=str(manifest_path) if manifest_path is not None else None,
        product_count=len(products),
        comparable_count=len(comparables),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _load_products(path: Path, errors: list[str]) -> list[Product]:
    records = _load_json_list(path, "products", errors)
    products = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            errors.append(f"products[{index}]: expected object")
            continue
        try:
            products.append(Product.from_mapping(record))
        except (TypeError, ValueError) as exc:
            errors.append(f"products[{index}]: {exc}")
    if not records:
        errors.append("products: expected at least one product")
    return products


def _load_comparables(path: Path, errors: list[str]) -> list[MarketComparable]:
    records = _load_json_list(path, "market_comps", errors)
    comparables = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            errors.append(f"market_comps[{index}]: expected object")
            continue
        try:
            comparable = MarketComparable.from_mapping(record)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"market_comps[{index}]: {exc}")
            continue
        if comparable.price <= 0:
            errors.append(f"market_comps[{index}]: price must be positive")
            continue
        comparables.append(comparable)
    if not records:
        errors.append("market_comps: expected at least one comparable")
    return comparables


def _load_json_list(path: Path, label: str, errors: list[str]) -> list[Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: cannot read JSON list from {path}: {exc}")
        return []
    if not isinstance(data, list):
        errors.append(f"{label}: expected JSON list")
        return []
    return data


def _validate_fixture_coverage(
    products: Sequence[Product],
    comparables: Sequence[MarketComparable],
    warnings: list[str],
) -> None:
    comparable_queries = {item.query for item in comparables}
    product_names = {product.name for product in products}
    for product in products:
        if product.name not in comparable_queries:
            warnings.append(
                f"product {product.id!r} has no exact comparable query match"
            )
    for query in sorted(comparable_queries - product_names):
        warnings.append(f"comparable query {query!r} has no product name match")


def _validate_manifest(
    *,
    manifest_path: Path,
    products_path: Path,
    comps_path: Path,
    product_count: int,
    comparables: Sequence[MarketComparable],
    errors: list[str],
    warnings: list[str],
) -> None:
    manifest = _load_json_object(manifest_path, "manifest", errors)
    if not manifest:
        return
    version = manifest.get("schema_version")
    if version != MARKET_DATASET_MANIFEST_SCHEMA_VERSION:
        errors.append(
            "manifest.schema_version: expected "
            f"{MARKET_DATASET_MANIFEST_SCHEMA_VERSION!r}, got {version!r}"
        )

    _compare_count(manifest, "product_count", product_count, errors)
    _compare_count(manifest, "comparable_count", len(comparables), errors)
    _validate_manifest_outputs(manifest, products_path, comps_path, warnings)
    _validate_manifest_input_hash(manifest, errors, warnings)
    _validate_manifest_quality(manifest, comparables, errors)
    _validate_manifest_privacy(manifest, errors)


def _load_json_object(
    path: Path,
    label: str,
    errors: list[str],
) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: cannot read JSON object from {path}: {exc}")
        return {}
    if not isinstance(data, Mapping):
        errors.append(f"{label}: expected JSON object")
        return {}
    return data


def _compare_count(
    manifest: Mapping[str, Any],
    key: str,
    expected: int,
    errors: list[str],
) -> None:
    observed = manifest.get(key)
    if observed != expected:
        errors.append(f"manifest.{key}: expected {expected}, got {observed!r}")


def _validate_manifest_outputs(
    manifest: Mapping[str, Any],
    products_path: Path,
    comps_path: Path,
    warnings: list[str],
) -> None:
    outputs = manifest.get("outputs", {})
    if not isinstance(outputs, Mapping):
        warnings.append("manifest.outputs: expected object")
        return
    _warn_if_path_differs(
        outputs.get("products"),
        products_path,
        "manifest.outputs.products",
        warnings,
    )
    _warn_if_path_differs(
        outputs.get("market_comps"),
        comps_path,
        "manifest.outputs.market_comps",
        warnings,
    )


def _warn_if_path_differs(
    observed: Any,
    expected: Path,
    label: str,
    warnings: list[str],
) -> None:
    if observed is None:
        warnings.append(f"{label}: missing")
        return
    if Path(str(observed)) != expected:
        warnings.append(f"{label}: records {observed!r}, validating {str(expected)!r}")


def _validate_manifest_input_hash(
    manifest: Mapping[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    input_data = manifest.get("input", {})
    if not isinstance(input_data, Mapping):
        errors.append("manifest.input: expected object")
        return
    raw_path = input_data.get("path")
    expected_hash = input_data.get("sha256")
    if not isinstance(raw_path, str) or not raw_path:
        warnings.append("manifest.input.path: missing; sha256 not rechecked")
        return
    if not isinstance(expected_hash, str) or not expected_hash:
        warnings.append("manifest.input.sha256: missing; sha256 not rechecked")
        return
    input_path = Path(raw_path)
    if not input_path.exists():
        warnings.append(
            f"manifest.input.path {str(input_path)!r} is unavailable; "
            "sha256 not rechecked"
        )
        return
    observed_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if observed_hash != expected_hash:
        errors.append("manifest.input.sha256: does not match current input file")


def _validate_manifest_quality(
    manifest: Mapping[str, Any],
    comparables: Sequence[MarketComparable],
    errors: list[str],
) -> None:
    quality = manifest.get("quality", {})
    if not isinstance(quality, Mapping):
        errors.append("manifest.quality: expected object")
        return
    price_summary = quality.get("price_summary", {})
    if not isinstance(price_summary, Mapping):
        errors.append("manifest.quality.price_summary: expected object")
        return
    prices = sorted(item.price for item in comparables)
    expected_count = len(prices)
    expected_median = round(statistics.median(prices), 2) if prices else 0.0
    if price_summary.get("count") != expected_count:
        errors.append(
            "manifest.quality.price_summary.count: expected "
            f"{expected_count}, got {price_summary.get('count')!r}"
        )
    observed_median = price_summary.get("median")
    if not isinstance(observed_median, (int, float)):
        errors.append("manifest.quality.price_summary.median: expected number")
    elif round(float(observed_median), 2) != expected_median:
        errors.append(
            "manifest.quality.price_summary.median: expected "
            f"{expected_median}, got {observed_median!r}"
        )


def _validate_manifest_privacy(
    manifest: Mapping[str, Any],
    errors: list[str],
) -> None:
    privacy = manifest.get("privacy", {})
    if not isinstance(privacy, Mapping):
        errors.append("manifest.privacy: expected object")
        return
    if privacy.get("contains_raw_listing_titles") is not False:
        errors.append("manifest.privacy.contains_raw_listing_titles must be false")
    if privacy.get("contains_credentials") is not False:
        errors.append("manifest.privacy.contains_credentials must be false")
