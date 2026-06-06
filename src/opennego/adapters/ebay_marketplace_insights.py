"""eBay Marketplace Insights ingestion adapter.

This adapter is intentionally outside the core environment. It fetches a
bounded sold-comps snapshot from eBay's official Marketplace Insights API and
then reuses the existing OpenNegotiation offline ingester to create normalized
benchmark fixtures.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib import error, parse, request

from opennego.artifacts import write_json
from opennego.market_ingestion import (
    MarketIngestionError,
    MarketIngestionResult,
    ingest_market_data,
)
from opennego.market_sources import (
    MarketSourcePolicyError,
    require_live_market_source_policy,
)
from opennego.schema import parse_price

EBAY_MARKETPLACE_INSIGHTS_SOURCE = "ebay_marketplace_insights"
EBAY_MARKETPLACE_INSIGHTS_SCHEMA_VERSION = (
    "opennego.ebay_marketplace_insights_ingestion.v1"
)

DEFAULT_MARKETPLACE_ID = "EBAY_US"
DEFAULT_LIMIT = 50
DEFAULT_WINDOW_DAYS = 90
DEFAULT_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
PRODUCTION_API_ROOT = "https://api.ebay.com"
SANDBOX_API_ROOT = "https://api.sandbox.ebay.com"
MARKETPLACE_INSIGHTS_PATH = "/buy/marketplace_insights/v1_beta/item_sales/search"


class EBayMarketplaceInsightsError(RuntimeError):
    """Raised when eBay Marketplace Insights ingestion cannot proceed."""


class EBayHttpClient(Protocol):
    """Small HTTP boundary used by tests and live adapter calls."""

    def post_form(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        form: Mapping[str, str],
    ) -> Mapping[str, Any]:
        ...

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str],
    ) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class EBayCredentials:
    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls) -> "EBayCredentials":
        client_id = os.environ.get("EBAY_CLIENT_ID")
        client_secret = os.environ.get("EBAY_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise EBayMarketplaceInsightsError(
                "eBay live ingestion requires EBAY_CLIENT_ID and "
                "EBAY_CLIENT_SECRET, or use --mock-response for no-key "
                "contract tests."
            )
        return cls(client_id=client_id, client_secret=client_secret)


@dataclass(frozen=True)
class EBayMarketplaceInsightsResult:
    schema_version: str
    query: str
    marketplace_id: str
    snapshot_output: str
    products_output: str
    comps_output: str
    comparable_count: int
    product_count: int
    manifest_output: str | None
    source_policy: str
    mode: str


class UrllibEBayHttpClient:
    """Minimal stdlib HTTP client to avoid adding runtime dependencies."""

    def post_form(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        form: Mapping[str, str],
    ) -> Mapping[str, Any]:
        body = parse.urlencode(form).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers=dict(headers),
            method="POST",
        )
        return _request_json(req)

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str],
    ) -> Mapping[str, Any]:
        separator = "&" if "?" in url else "?"
        full_url = url + separator + parse.urlencode(params)
        req = request.Request(full_url, headers=dict(headers), method="GET")
        return _request_json(req)


def fetch_ebay_marketplace_insights_records(
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
) -> list[Mapping[str, Any]]:
    """Fetch and normalize eBay sold-comps records.

    When ``mock_response_path`` is provided, no network call or credential lookup
    occurs. This lets CI exercise the same parsing contract without secrets.
    """

    _validate_query(query)
    _validate_limit(limit)
    require_live_market_source_policy(
        source_policy_path,
        expected_adapter_kind=EBAY_MARKETPLACE_INSIGHTS_SOURCE,
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
        payload = _search_marketplace_insights(
            query=query,
            marketplace_id=marketplace_id,
            limit=limit,
            category_ids=category_ids,
            item_filter=item_filter,
            environment=environment,
            access_token=token,
            client=http_client,
        )
    records = _records_from_marketplace_insights_payload(
        payload,
        query=query,
        fallback_marketplace=marketplace_id,
    )
    if not records:
        raise EBayMarketplaceInsightsError(
            "eBay Marketplace Insights returned no sold-comps records"
        )
    return records[:limit]


def ingest_ebay_marketplace_insights(
    *,
    query: str,
    source_policy_path: str | Path,
    snapshot_output: str | Path,
    products_output: str | Path,
    comps_output: str | Path,
    manifest_output: str | Path | None = None,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    limit: int = DEFAULT_LIMIT,
    category_ids: Sequence[str] = (),
    item_filter: Sequence[str] = (),
    environment: str = "production",
    credentials: EBayCredentials | None = None,
    client: EBayHttpClient | None = None,
    access_token: str | None = None,
    mock_response_path: str | Path | None = None,
    currency: str = "USD",
    window_days: int | None = DEFAULT_WINDOW_DAYS,
    asking_multiplier: float = 1.25,
    buyer_budget_multiplier: float = 1.2,
) -> EBayMarketplaceInsightsResult:
    """Fetch eBay sold-comps data and write OpenNegotiation market fixtures."""

    records = fetch_ebay_marketplace_insights_records(
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
    )
    snapshot_path = Path(snapshot_output)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(snapshot_path, records)
    try:
        ingested = ingest_market_data(
            input_path=snapshot_path,
            products_output=products_output,
            comps_output=comps_output,
            source=EBAY_MARKETPLACE_INSIGHTS_SOURCE,
            currency=currency,
            window_days=window_days,
            asking_multiplier=asking_multiplier,
            buyer_budget_multiplier=buyer_budget_multiplier,
            manifest_output=manifest_output,
            source_policy_path=source_policy_path,
        )
    except (MarketIngestionError, MarketSourcePolicyError) as exc:
        raise EBayMarketplaceInsightsError(str(exc)) from exc
    return _result_from_ingestion(
        query=query,
        marketplace_id=marketplace_id,
        snapshot_path=snapshot_path,
        ingested=ingested,
        source_policy_path=source_policy_path,
        mode="mock_response" if mock_response_path is not None else "official_api",
    )


def _mint_application_token(
    *,
    environment: str,
    credentials: EBayCredentials,
    client: EBayHttpClient,
) -> str:
    api_root = _api_root(environment)
    raw_credentials = f"{credentials.client_id}:{credentials.client_secret}".encode(
        "utf-8"
    )
    auth = base64.b64encode(raw_credentials).decode("ascii")
    payload = client.post_form(
        f"{api_root}/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        form={
            "grant_type": "client_credentials",
            "scope": DEFAULT_OAUTH_SCOPE,
        },
    )
    token = payload.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise EBayMarketplaceInsightsError(
            "eBay OAuth response did not include access_token"
        )
    return token


def _search_marketplace_insights(
    *,
    query: str,
    marketplace_id: str,
    limit: int,
    category_ids: Sequence[str],
    item_filter: Sequence[str],
    environment: str,
    access_token: str,
    client: EBayHttpClient,
) -> Mapping[str, Any]:
    params: dict[str, str] = {"q": query, "limit": str(limit)}
    if category_ids:
        params["category_ids"] = ",".join(category_ids)
    if item_filter:
        params["filter"] = ",".join(item_filter)
    return client.get_json(
        _api_root(environment) + MARKETPLACE_INSIGHTS_PATH,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
        },
        params=params,
    )


def _records_from_marketplace_insights_payload(
    payload: Mapping[str, Any],
    *,
    query: str,
    fallback_marketplace: str,
) -> list[Mapping[str, Any]]:
    raw_items = _item_list(payload)
    records: list[Mapping[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            continue
        price, currency = _extract_price(item, index)
        records.append(
            {
                "query": query,
                "title": _extract_string(item, ("title", "itemTitle", "name"))
                or query,
                "price": price,
                "condition": _extract_condition(item),
                "source": EBAY_MARKETPLACE_INSIGHTS_SOURCE,
                "currency": currency or "USD",
                "sale_mechanism": _extract_sale_mechanism(item),
                "sold_at": _extract_string(
                    item,
                    (
                        "soldDate",
                        "lastSoldDate",
                        "itemEndDate",
                        "endDate",
                        "transactionDate",
                    ),
                ),
                "marketplace": _extract_string(
                    item,
                    ("marketplaceId", "marketplace", "site"),
                )
                or fallback_marketplace,
            }
        )
    return records


def _item_list(payload: Mapping[str, Any]) -> Sequence[Any]:
    for key in (
        "itemSales",
        "item_sales",
        "itemSummaries",
        "items",
        "sales",
        "results",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    raise EBayMarketplaceInsightsError(
        "eBay Marketplace Insights response did not include an item sales list"
    )


def _extract_price(item: Mapping[str, Any], index: int) -> tuple[float, str | None]:
    for key in (
        "price",
        "soldPrice",
        "lastSoldPrice",
        "itemPrice",
        "finalPrice",
        "convertedFromPrice",
    ):
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, Mapping):
            raw_value = value.get("value") or value.get("convertedFromValue")
            currency = value.get("currency") or value.get("currencyId")
        else:
            raw_value = value
            currency = item.get("currency")
        try:
            price = parse_price(raw_value)
        except (TypeError, ValueError) as exc:
            raise EBayMarketplaceInsightsError(
                f"itemSales[{index}].{key}: price is not parseable"
            ) from exc
        if price <= 0:
            raise EBayMarketplaceInsightsError(
                f"itemSales[{index}].{key}: price must be positive"
            )
        return price, str(currency) if currency else None
    raise EBayMarketplaceInsightsError(
        f"itemSales[{index}]: missing sold price field"
    )


def _extract_condition(item: Mapping[str, Any]) -> str:
    condition = _extract_string(item, ("condition", "itemCondition"))
    if condition:
        return condition
    condition_id = _extract_string(item, ("conditionId",))
    return f"condition_{condition_id}" if condition_id else "unknown"


def _extract_sale_mechanism(item: Mapping[str, Any]) -> str:
    direct = _extract_string(item, ("saleMechanism", "listingType", "format"))
    if direct:
        return direct
    buying_options = item.get("buyingOptions")
    if isinstance(buying_options, Sequence) and not isinstance(
        buying_options,
        (str, bytes),
    ):
        return "+".join(str(option).lower() for option in buying_options) or "mixed"
    return "mixed"


def _extract_string(item: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _read_mock_response(path: str | Path) -> Mapping[str, Any]:
    mock_path = Path(path)
    try:
        payload = json.loads(mock_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EBayMarketplaceInsightsError(
            f"{mock_path}: expected eBay Marketplace Insights JSON response"
        ) from exc
    if not isinstance(payload, Mapping):
        raise EBayMarketplaceInsightsError(
            f"{mock_path}: expected JSON object response"
        )
    return payload


def _api_root(environment: str) -> str:
    normalized = environment.lower().strip()
    if normalized == "production":
        return PRODUCTION_API_ROOT
    if normalized == "sandbox":
        return SANDBOX_API_ROOT
    raise EBayMarketplaceInsightsError(
        "environment must be either 'production' or 'sandbox'"
    )


def _validate_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise EBayMarketplaceInsightsError("query must be a non-empty string")


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > 200:
        raise EBayMarketplaceInsightsError("limit must be between 1 and 200")


def _request_json(req: request.Request) -> Mapping[str, Any]:
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EBayMarketplaceInsightsError(
            f"eBay API request failed with HTTP {exc.code}: {detail[:500]}"
        ) from exc
    except error.URLError as exc:
        raise EBayMarketplaceInsightsError(f"eBay API request failed: {exc}") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise EBayMarketplaceInsightsError(
            "eBay API response was not valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise EBayMarketplaceInsightsError("eBay API response must be a JSON object")
    return payload


def _result_from_ingestion(
    *,
    query: str,
    marketplace_id: str,
    snapshot_path: Path,
    ingested: MarketIngestionResult,
    source_policy_path: str | Path,
    mode: str,
) -> EBayMarketplaceInsightsResult:
    return EBayMarketplaceInsightsResult(
        schema_version=EBAY_MARKETPLACE_INSIGHTS_SCHEMA_VERSION,
        query=query,
        marketplace_id=marketplace_id,
        snapshot_output=str(snapshot_path),
        products_output=ingested.products_output,
        comps_output=ingested.comps_output,
        comparable_count=ingested.comparable_count,
        product_count=ingested.product_count,
        manifest_output=ingested.manifest_output,
        source_policy=str(source_policy_path),
        mode=mode,
    )
