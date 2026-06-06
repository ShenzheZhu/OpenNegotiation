import json

from opennego.adapters.ebay_marketplace_insights import (
    EBayCredentials,
    EBayMarketplaceInsightsError,
    fetch_ebay_marketplace_insights_records,
)
from opennego.cli import main
from opennego.market_sources import write_market_source_policy


def test_ebay_marketplace_insights_fetch_uses_official_api_contract(tmp_path):
    policy_path = _write_live_policy(tmp_path)
    client = _FakeEBayClient(
        {
            "itemSales": [
                {
                    "title": "Apple iPhone 14 Pro 128GB Unlocked",
                    "price": {"value": "575.00", "currency": "USD"},
                    "condition": "Used",
                    "buyingOptions": ["FIXED_PRICE"],
                    "itemEndDate": "2026-05-01T12:00:00Z",
                    "marketplaceId": "EBAY_US",
                }
            ]
        }
    )

    records = fetch_ebay_marketplace_insights_records(
        query="Apple iPhone 14 Pro 128GB Unlocked",
        source_policy_path=policy_path,
        marketplace_id="EBAY_US",
        limit=25,
        category_ids=("9355",),
        item_filter=("conditions:{USED}",),
        credentials=EBayCredentials("client-id", "client-secret"),
        client=client,
    )

    assert records == [
        {
            "query": "Apple iPhone 14 Pro 128GB Unlocked",
            "title": "Apple iPhone 14 Pro 128GB Unlocked",
            "price": 575.0,
            "condition": "Used",
            "source": "ebay_marketplace_insights",
            "currency": "USD",
            "sale_mechanism": "fixed_price",
            "sold_at": "2026-05-01T12:00:00Z",
            "marketplace": "EBAY_US",
        }
    ]
    assert client.token_request["form"]["grant_type"] == "client_credentials"
    assert client.search_request["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
    assert client.search_request["params"] == {
        "q": "Apple iPhone 14 Pro 128GB Unlocked",
        "limit": "25",
        "category_ids": "9355",
        "filter": "conditions:{USED}",
    }


def test_ingest_ebay_cli_mock_response_writes_normalized_fixtures(tmp_path, capsys):
    policy_path = _write_live_policy(tmp_path)
    mock_response = tmp_path / "ebay_response.json"
    snapshot_path = tmp_path / "ebay_snapshot.json"
    products_path = tmp_path / "products.json"
    comps_path = tmp_path / "market_comps.json"
    manifest_path = tmp_path / "market_manifest.json"
    mock_response.write_text(
        json.dumps(
            {
                "itemSales": [
                    {
                        "title": "iPhone 14 Pro clean IMEI",
                        "price": {"value": "555.00", "currency": "USD"},
                        "condition": "used_good",
                        "saleMechanism": "best_offer",
                        "soldDate": "2026-05-01",
                    },
                    {
                        "title": "Unlocked iPhone 14 Pro",
                        "soldPrice": {"value": "575.00", "currency": "USD"},
                        "condition": "used_good",
                        "saleMechanism": "buy_it_now",
                        "soldDate": "2026-05-03",
                    },
                    {
                        "title": "iPhone 14 Pro 128GB",
                        "lastSoldPrice": {"value": "610.00", "currency": "USD"},
                        "condition": "used_good",
                        "saleMechanism": "buy_it_now",
                        "soldDate": "2026-05-06",
                    },
                ]
            }
        )
        + "\n"
    )

    exit_code = main(
        [
            "ingest-ebay",
            "--query",
            "Apple iPhone 14 Pro 128GB Unlocked",
            "--source-policy",
            str(policy_path),
            "--snapshot-output",
            str(snapshot_path),
            "--products-output",
            str(products_path),
            "--comps-output",
            str(comps_path),
            "--manifest-output",
            str(manifest_path),
            "--mock-response",
            str(mock_response),
            "--limit",
            "50",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    products = json.loads(products_path.read_text())
    comps = json.loads(comps_path.read_text())
    manifest = json.loads(manifest_path.read_text())

    assert exit_code == 0
    assert payload["mode"] == "mock_response"
    assert payload["comparable_count"] == 3
    assert payload["snapshot_output"] == str(snapshot_path)
    assert products[0]["market_reference"]["reference_price"] == 575.0
    assert products[0]["market_reference"]["sample_size"] == 3
    assert comps[0]["source"] == "ebay_marketplace_insights"
    assert manifest["source_policy"]["collection_mode"] == "official_api"
    assert manifest["source_policy"]["live_collection_enabled"] is True
    assert manifest["privacy"]["contains_credentials"] is False


def test_ebay_ingestion_requires_live_source_policy(tmp_path):
    policy_path = tmp_path / "offline_source_policy.json"
    write_market_source_policy(
        policy_path,
        source_id="ebay_offline_export",
        adapter_kind="offline_export",
        collection_mode="offline_export",
        data_rights="user_provided_export",
    )
    mock_response = tmp_path / "ebay_response.json"
    mock_response.write_text('{"itemSales": []}\n')

    try:
        fetch_ebay_marketplace_insights_records(
            query="iPhone",
            source_policy_path=policy_path,
            mock_response_path=mock_response,
        )
    except EBayMarketplaceInsightsError as exc:
        raise AssertionError("expected source policy error, not adapter error") from exc
    except ValueError as exc:
        assert "live ingestion requires collection_mode" in str(exc)
    else:
        raise AssertionError("expected unsafe live policy to fail")


def test_ebay_live_fetch_requires_credentials_when_not_mocked(tmp_path, monkeypatch):
    policy_path = _write_live_policy(tmp_path)
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)

    try:
        fetch_ebay_marketplace_insights_records(
            query="iPhone",
            source_policy_path=policy_path,
        )
    except EBayMarketplaceInsightsError as exc:
        assert "requires EBAY_CLIENT_ID and EBAY_CLIENT_SECRET" in str(exc)
    else:
        raise AssertionError("expected missing eBay credentials to fail")


class _FakeEBayClient:
    def __init__(self, response):
        self.response = response
        self.token_request = {}
        self.search_request = {}

    def post_form(self, url, *, headers, form):
        self.token_request = {
            "url": url,
            "headers": dict(headers),
            "form": dict(form),
        }
        return {"access_token": "fake-token"}

    def get_json(self, url, *, headers, params):
        self.search_request = {
            "url": url,
            "headers": dict(headers),
            "params": dict(params),
        }
        return self.response


def _write_live_policy(tmp_path):
    policy_path = tmp_path / "ebay_source_policy.json"
    write_market_source_policy(
        policy_path,
        source_id="ebay_marketplace_insights",
        adapter_kind="ebay_marketplace_insights",
        collection_mode="official_api",
        data_rights="official_ebay_api_with_marketplace_insights_access",
        terms_url="https://developer.ebay.com/api-docs/buy/marketplace-insights/static/overview.html",
        privacy_classification="official_api_sold_comps_without_account_pii",
        live_collection_enabled=True,
        retention_policy="cache_sanitized_snapshots_only; no_credentials_in_repo",
    )
    return policy_path
