"""Offline sold-comps ingestion for OpenNegotiation market fixtures."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import write_json
from opennego.schema import parse_price

MARKET_INGESTION_SCHEMA_VERSION = "opennego.market_ingestion.v1"
MARKET_DATASET_MANIFEST_SCHEMA_VERSION = "opennego.market_dataset_manifest.v1"

QUERY_KEYS = ("query", "product_name", "product", "cluster", "name")
TITLE_KEYS = ("title", "listing_title", "item_title", "name")
PRICE_KEYS = ("price", "sold_price", "final_price", "sale_price")
CONDITION_KEYS = ("condition", "item_condition")
SOURCE_KEYS = ("source", "marketplace", "platform")
SALE_MECHANISM_KEYS = ("sale_mechanism", "format", "listing_type")
CURRENCY_KEYS = ("currency",)
SOLD_AT_KEYS = ("sold_at", "sale_date", "ended_at", "date")


class MarketIngestionError(ValueError):
    """Raised when offline sold-comps data cannot be normalized."""


@dataclass(frozen=True)
class MarketIngestionResult:
    schema_version: str
    input_path: str
    products_output: str
    comps_output: str
    product_count: int
    comparable_count: int
    manifest_output: str | None = None


def ingest_market_data(
    *,
    input_path: str | Path,
    products_output: str | Path,
    comps_output: str | Path,
    source: str = "offline_sold_comps",
    currency: str = "USD",
    window_days: int | None = None,
    asking_multiplier: float = 1.25,
    buyer_budget_multiplier: float = 1.2,
    manifest_output: str | Path | None = None,
) -> MarketIngestionResult:
    """Normalize a local CSV/JSON sold-comps export into OpenNegotiation fixtures."""

    source_path = Path(input_path)
    records = _read_records(source_path)
    comparables = [
        _normalize_record(record, index, source, currency)
        for index, record in enumerate(records)
    ]
    if not comparables:
        raise MarketIngestionError("input must contain at least one comparable")
    products = _product_records(
        comparables,
        source=source,
        fallback_currency=currency,
        window_days=window_days,
        asking_multiplier=asking_multiplier,
        buyer_budget_multiplier=buyer_budget_multiplier,
    )
    products_path = Path(products_output)
    comps_path = Path(comps_output)
    products_path.parent.mkdir(parents=True, exist_ok=True)
    comps_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(products_path, products)
    write_json(comps_path, [_comparable_output(record) for record in comparables])
    manifest_path = Path(manifest_output) if manifest_output is not None else None
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            manifest_path,
            _dataset_manifest(
                input_path=source_path,
                products_output=products_path,
                comps_output=comps_path,
                source=source,
                fallback_currency=currency,
                window_days=window_days,
                products=products,
                comparables=comparables,
            ),
        )
    return MarketIngestionResult(
        schema_version=MARKET_INGESTION_SCHEMA_VERSION,
        input_path=str(input_path),
        products_output=str(products_path),
        comps_output=str(comps_path),
        product_count=len(products),
        comparable_count=len(comparables),
        manifest_output=str(manifest_path) if manifest_path is not None else None,
    )


@dataclass(frozen=True)
class NormalizedComparable:
    query: str
    title: str
    price: float
    condition: str
    source: str
    currency: str
    sale_mechanism: str
    sold_at: str | None


def _read_records(path: Path) -> list[Mapping[str, Any]]:
    if not path.exists():
        raise MarketIngestionError(f"{path}: input file does not exist")
    if path.suffix.lower() == ".csv":
        with path.open(newline="") as handle:
            records = list(csv.DictReader(handle))
        if not records:
            raise MarketIngestionError(f"{path}: CSV contains no rows")
        return records
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise MarketIngestionError(f"{path}: expected CSV or JSON list") from exc
    if not isinstance(data, list) or not data:
        raise MarketIngestionError(f"{path}: expected non-empty JSON list")
    if not all(isinstance(item, Mapping) for item in data):
        raise MarketIngestionError(f"{path}: expected JSON list of objects")
    return list(data)


def _normalize_record(
    record: Mapping[str, Any],
    index: int,
    fallback_source: str,
    fallback_currency: str,
) -> NormalizedComparable:
    query = _required_alias(record, QUERY_KEYS, index, "product/query")
    title = _optional_alias(record, TITLE_KEYS) or query
    price_value = _required_alias(record, PRICE_KEYS, index, "sold/final price")
    condition = _optional_alias(record, CONDITION_KEYS) or "unknown"
    source = _optional_alias(record, SOURCE_KEYS) or fallback_source
    currency = _optional_alias(record, CURRENCY_KEYS) or fallback_currency
    sale_mechanism = _optional_alias(record, SALE_MECHANISM_KEYS) or "mixed"
    sold_at = _optional_alias(record, SOLD_AT_KEYS)
    try:
        price = parse_price(price_value)
    except (TypeError, ValueError) as exc:
        raise MarketIngestionError(
            f"row {index}: sold/final price is not parseable: {price_value!r}"
        ) from exc
    if price <= 0:
        raise MarketIngestionError(f"row {index}: price must be positive")
    return NormalizedComparable(
        query=str(query),
        title=str(title),
        price=price,
        condition=str(condition),
        source=str(source),
        currency=str(currency),
        sale_mechanism=str(sale_mechanism),
        sold_at=str(sold_at) if sold_at else None,
    )


def _product_records(
    comparables: Sequence[NormalizedComparable],
    *,
    source: str,
    fallback_currency: str,
    window_days: int | None,
    asking_multiplier: float,
    buyer_budget_multiplier: float,
) -> list[Mapping[str, Any]]:
    products = []
    for query in sorted({item.query for item in comparables}):
        items = [item for item in comparables if item.query == query]
        prices = sorted(item.price for item in items)
        reference_price = round(statistics.median(prices), 2)
        p25 = round(_percentile(prices, 0.25), 2)
        p75 = round(_percentile(prices, 0.75), 2)
        condition = _mode([item.condition for item in items]) or "unknown"
        currency = _mode([item.currency for item in items]) or fallback_currency
        mechanisms = sorted({item.sale_mechanism for item in items if item.sale_mechanism})
        sale_mechanism = mechanisms[0] if len(mechanisms) == 1 else "mixed"
        product_id = _slug(query)
        products.append(
            {
                "id": product_id,
                "name": query,
                "description": f"Offline sold-comps cluster for {query}.",
                "condition": condition,
                "asking_price": round(reference_price * asking_multiplier, 2),
                "buyer_budget": round(reference_price * buyer_budget_multiplier, 2),
                "synthetic_seller_reservation_price": p25,
                "market_reference": {
                    "reference_price": reference_price,
                    "p25_price": p25,
                    "p75_price": p75,
                    "sample_size": len(items),
                    "currency": currency,
                    "window_days": window_days,
                    "source": source,
                    "sale_mechanism": sale_mechanism,
                    "metadata": {
                        "schema_version": MARKET_INGESTION_SCHEMA_VERSION,
                        "generated_from": "offline_sold_comps",
                        "source_record_count": len(items),
                    },
                },
            }
        )
    return products


def _comparable_output(record: NormalizedComparable) -> Mapping[str, Any]:
    payload: dict[str, Any] = {
        "query": record.query,
        "title": record.title,
        "condition": record.condition,
        "price": record.price,
        "source": record.source,
        "currency": record.currency,
        "sale_mechanism": record.sale_mechanism,
    }
    if record.sold_at is not None:
        payload["sold_at"] = record.sold_at
    return payload


def _dataset_manifest(
    *,
    input_path: Path,
    products_output: Path,
    comps_output: Path,
    source: str,
    fallback_currency: str,
    window_days: int | None,
    products: Sequence[Mapping[str, Any]],
    comparables: Sequence[NormalizedComparable],
) -> Mapping[str, Any]:
    prices = sorted(record.price for record in comparables)
    return {
        "schema_version": MARKET_DATASET_MANIFEST_SCHEMA_VERSION,
        "ingestion_schema_version": MARKET_INGESTION_SCHEMA_VERSION,
        "input": {
            "path": str(input_path),
            "sha256": _sha256(input_path),
            "format": _input_format(input_path),
        },
        "outputs": {
            "products": str(products_output),
            "market_comps": str(comps_output),
        },
        "source": source,
        "fallback_currency": fallback_currency,
        "window_days": window_days,
        "product_count": len(products),
        "comparable_count": len(comparables),
        "quality": {
            "missing_sold_at_count": sum(
                1 for record in comparables if record.sold_at is None
            ),
            "price_summary": _price_summary(prices),
            "counts_by_source": _counts(record.source for record in comparables),
            "counts_by_currency": _counts(record.currency for record in comparables),
            "counts_by_condition": _counts(record.condition for record in comparables),
            "counts_by_sale_mechanism": _counts(
                record.sale_mechanism for record in comparables
            ),
            "clusters": _cluster_summaries(products, comparables),
        },
        "privacy": {
            "contains_raw_listing_titles": False,
            "contains_credentials": False,
        },
    }


def _cluster_summaries(
    products: Sequence[Mapping[str, Any]],
    comparables: Sequence[NormalizedComparable],
) -> list[Mapping[str, Any]]:
    summaries = []
    for product in products:
        name = str(product["name"])
        items = [record for record in comparables if record.query == name]
        prices = sorted(record.price for record in items)
        market_reference = product.get("market_reference", {})
        summaries.append(
            {
                "product_id": product["id"],
                "name": name,
                "sample_size": len(items),
                "reference_price": market_reference.get("reference_price"),
                "p25_price": market_reference.get("p25_price"),
                "p75_price": market_reference.get("p75_price"),
                "price_summary": _price_summary(prices),
                "counts_by_source": _counts(record.source for record in items),
                "counts_by_condition": _counts(record.condition for record in items),
                "counts_by_sale_mechanism": _counts(
                    record.sale_mechanism for record in items
                ),
            }
        )
    return summaries


def _price_summary(prices: Sequence[float]) -> Mapping[str, float | int]:
    if not prices:
        return {
            "count": 0,
            "min": 0.0,
            "p25": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "max": 0.0,
        }
    return {
        "count": len(prices),
        "min": round(prices[0], 2),
        "p25": round(_percentile(prices, 0.25), 2),
        "median": round(statistics.median(prices), 2),
        "p75": round(_percentile(prices, 0.75), 2),
        "max": round(prices[-1], 2),
    }


def _counts(values) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    return suffix.lstrip(".") or "unknown"


def _required_alias(
    record: Mapping[str, Any],
    aliases: Sequence[str],
    index: int,
    label: str,
) -> Any:
    value = _optional_alias(record, aliases)
    if value is None:
        raise MarketIngestionError(
            f"row {index}: expected {label} field; tried {', '.join(aliases)}"
        )
    return value


def _optional_alias(record: Mapping[str, Any], aliases: Sequence[str]) -> Any | None:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for alias in aliases:
        value = lowered.get(alias)
        if value is not None and value != "":
            return value
    return None


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise MarketIngestionError("cannot compute percentile of empty values")
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _mode(values: Sequence[str]) -> str | None:
    present = [value for value in values if value]
    if not present:
        return None
    counts = {value: present.count(value) for value in set(present)}
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.lower()).strip("-._")
    if not slug:
        raise MarketIngestionError("generated empty product id")
    return slug
