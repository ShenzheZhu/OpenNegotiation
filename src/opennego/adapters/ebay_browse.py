"""eBay Browse API active-listing ingestion adapter.

Fetches a bounded snapshot of live listings from eBay's official Browse API
and writes normalized ``active_listing_search`` fixture records. Like the
Marketplace Insights adapter, it sits behind the market source-policy gates,
keeps a ``mock_response_path`` contract-test path that needs no credentials,
and whitelists output fields so no usernames, raw HTML, or tracking state
leave the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.adapters.ebay_marketplace_insights import (
    EBayCredentials,
    EBayHttpClient,
    UrllibEBayHttpClient,
    _mint_application_token,
    _read_mock_response,
)
from opennego.artifacts import write_json
from opennego.market_sources import require_live_market_source_policy
from opennego.schema import parse_price

EBAY_BROWSE_SOURCE = "ebay_browse"
EBAY_BROWSE_SCHEMA_VERSION = "opennego.ebay_browse_ingestion.v1"

DEFAULT_MARKETPLACE_ID = "EBAY_US"
DEFAULT_LIMIT = 50
PRODUCTION_API_ROOT = "https://api.ebay.com"
SANDBOX_API_ROOT = "https://api.sandbox.ebay.com"
BROWSE_SEARCH_PATH = "/buy/browse/v1/item_summary/search"


class EBayBrowseError(RuntimeError):
    """Raised when eBay Browse ingestion cannot proceed."""


@dataclass(frozen=True)
class EBayBrowseResult:
    schema_version: str
    query: str
    marketplace_id: str
    snapshot_output: str
    listings_output: str
    listing_count: int
    source_policy: str
    mode: str


def fetch_ebay_browse_listings(
    *,
    query: str,
    source_policy_path: str | Path,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    limit: int = DEFAULT_LIMIT,
    category_ids: Sequence[str] = (),
    item_filter: Sequence[str] = (),
    environment: str = "production",
    credentials: EBayCredentials | None = None,
    client: EBayHttpClient | None = None,
    access_token: str | None = None,
    mock_response_path: str | Path | None = None,
    as_of: str | None = None,
) -> list[Mapping[str, Any]]:
    """Fetch and normalize active-listing records.

    ``as_of`` (ISO date) makes ``listing_age_days`` deterministic for tests;
    when omitted, listing age derives from today's date.
    """

    if not query or not query.strip():
        raise EBayBrowseError("query must be a non-empty string")
    if limit <= 0:
        raise EBayBrowseError("limit must be positive")
    require_live_market_source_policy(
        source_policy_path,
        expected_adapter_kind=EBAY_BROWSE_SOURCE,
    )
    if mock_response_path is not None:
        payload = _read_mock_response(mock_response_path)
    else:
        http_client = client or UrllibEBayHttpClient()
        token = access_token or _mint_application_token(
            environment=environment,
            credentials=credentials or EBayCredentials.from_env(),
            client=http_client,
        )
        api_root = (
            SANDBOX_API_ROOT if environment == "sandbox" else PRODUCTION_API_ROOT
        )
        params: dict[str, str] = {"q": query, "limit": str(limit)}
        if category_ids:
            params["category_ids"] = ",".join(category_ids)
        if item_filter:
            params["filter"] = ",".join(item_filter)
        payload = http_client.get_json(
            api_root + BROWSE_SEARCH_PATH,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
            },
            params=params,
        )
    records = _records_from_browse_payload(
        payload,
        query=query,
        as_of=as_of,
    )
    if not records:
        raise EBayBrowseError("eBay Browse returned no active listings")
    return records[:limit]


def ingest_ebay_browse_listings(
    *,
    query: str,
    source_policy_path: str | Path,
    snapshot_output: str | Path,
    listings_output: str | Path,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    limit: int = DEFAULT_LIMIT,
    category_ids: Sequence[str] = (),
    item_filter: Sequence[str] = (),
    environment: str = "production",
    credentials: EBayCredentials | None = None,
    client: EBayHttpClient | None = None,
    access_token: str | None = None,
    mock_response_path: str | Path | None = None,
    as_of: str | None = None,
) -> EBayBrowseResult:
    """Fetch active listings and write tool-ready fixture records."""

    records = fetch_ebay_browse_listings(
        query=query,
        source_policy_path=source_policy_path,
        marketplace_id=marketplace_id,
        limit=limit,
        category_ids=category_ids,
        item_filter=item_filter,
        environment=environment,
        credentials=credentials,
        client=client,
        access_token=access_token,
        mock_response_path=mock_response_path,
        as_of=as_of,
    )
    snapshot_path = Path(snapshot_output)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        snapshot_path,
        {
            "schema_version": EBAY_BROWSE_SCHEMA_VERSION,
            "query": query,
            "marketplace_id": marketplace_id,
            "listing_count": len(records),
            "records": records,
        },
    )
    listings_path = Path(listings_output)
    listings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(listings_path, records)
    return EBayBrowseResult(
        schema_version=EBAY_BROWSE_SCHEMA_VERSION,
        query=query,
        marketplace_id=marketplace_id,
        snapshot_output=str(snapshot_path),
        listings_output=str(listings_path),
        listing_count=len(records),
        source_policy=str(source_policy_path),
        mode="mock_response" if mock_response_path is not None else "official_api",
    )


def _records_from_browse_payload(
    payload: Mapping[str, Any],
    *,
    query: str,
    as_of: str | None,
) -> list[Mapping[str, Any]]:
    summaries = payload.get("itemSummaries")
    if not isinstance(summaries, list):
        return []
    records = []
    for summary in summaries:
        if not isinstance(summary, Mapping):
            continue
        price = _price_value(summary.get("price"))
        title = summary.get("title")
        if price is None or not title:
            continue
        records.append(
            {
                "query": query,
                "title": str(title),
                "asking_price": price,
                "currency": _currency_value(summary.get("price")),
                "condition": str(summary.get("condition", "unknown")).lower(),
                "listing_age_days": _listing_age_days(
                    summary.get("itemCreationDate"), as_of
                ),
                "shipping_cost": _shipping_cost(summary.get("shippingOptions")),
                "seller_rating_band": _seller_rating_band(summary.get("seller")),
                "source": EBAY_BROWSE_SOURCE,
            }
        )
    return records


def _price_value(price: Any) -> float | None:
    if not isinstance(price, Mapping) or price.get("value") is None:
        return None
    try:
        return parse_price(price["value"])
    except (TypeError, ValueError):
        return None


def _currency_value(price: Any) -> str:
    if isinstance(price, Mapping) and price.get("currency"):
        return str(price["currency"])
    return "USD"


def _listing_age_days(creation_date: Any, as_of: str | None) -> int | None:
    if not creation_date:
        return None
    try:
        created = datetime.fromisoformat(
            str(creation_date).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None
    reference = date.fromisoformat(as_of) if as_of else date.today()
    return max(0, (reference - created).days)


def _shipping_cost(shipping_options: Any) -> float | None:
    if not isinstance(shipping_options, list):
        return None
    for option in shipping_options:
        if not isinstance(option, Mapping):
            continue
        cost = option.get("shippingCost")
        if isinstance(cost, Mapping) and cost.get("value") is not None:
            try:
                return parse_price(cost["value"])
            except (TypeError, ValueError):
                continue
    return None


def _seller_rating_band(seller: Any) -> str:
    if not isinstance(seller, Mapping):
        return "unknown"
    feedback = seller.get("feedbackPercentage")
    if feedback is None:
        return "unknown"
    try:
        score = float(feedback)
    except (TypeError, ValueError):
        return "unknown"
    if score >= 99.0:
        return "high"
    if score >= 95.0:
        return "medium"
    return "low"
