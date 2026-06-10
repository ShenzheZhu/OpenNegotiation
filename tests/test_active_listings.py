import json

import pytest

from opennego.adapters.ebay_browse import (
    EBayBrowseError,
    fetch_ebay_browse_listings,
    ingest_ebay_browse_listings,
)
from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.cli import main
from opennego.environment import NegotiationEnvironment, ToolRuntimeConfig
from opennego.market_sources import MarketSourcePolicyError, write_market_source_policy
from opennego.market_validation import validate_market_dataset
from opennego.runner import run_experiment_config
from opennego.scenario_generator import generate_scenarios, load_products
from opennego.schema import Role
from opennego.tools import ActiveListingTool

LISTINGS_FIXTURE = "examples/data/scenario_seed_active_listings.json"


def test_tool_returns_listing_cards_with_spread_stats():
    tool = ActiveListingTool.from_json(LISTINGS_FIXTURE)

    result = tool.call(
        {"query": "Apple iPhone 14 Pro 128GB Unlocked", "limit": 3}, None
    )

    assert result["ok"] is True
    assert result["count"] == 3
    assert result["median_asking_price"] > 0
    assert result["median_listing_age_days"] is not None
    first = result["results"][0]
    assert {
        "title",
        "asking_price",
        "condition",
        "listing_age_days",
        "shipping_cost",
        "seller_rating_band",
        "source",
    } <= set(first)
    assert result["provenance"][0]["source"] == "fixture-active-listing"


def test_tool_respects_private_visibility_in_environment():
    scenario = generate_scenarios(
        load_products("examples/data/scenario_seed_products.json"), seed=13
    )[0]
    tool = ActiveListingTool.from_json(LISTINGS_FIXTURE)
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(tool,),
        tool_configs=(
            ToolRuntimeConfig(
                name="active_listing_search",
                roles=(Role.BUYER,),
                visibility="private",
            ),
        ),
    )

    assert "active_listing_search" in env._context_for(Role.BUYER).available_tools
    assert (
        "active_listing_search"
        not in env._context_for(Role.SELLER).available_tools
    )


def test_runner_builds_active_listings_tool_regime(tmp_path):
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "active_listings_smoke",
        "output_dir": str(tmp_path / "runs"),
        "seeds": [7],
        "agents": {
            "buyer": {"kind": "tool_aware_buyer"},
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": [
            {
                "id": "iphone",
                "products_file": "examples/data/scenario_seed_products.json",
                "product_index": 0,
                "max_turns": 8,
            }
        ],
        "tool_regimes": [
            {
                "id": "buyer_private_active_listings",
                "tools": [
                    {
                        "name": "active_listing_search",
                        "kind": "active_listings",
                        "source": LISTINGS_FIXTURE,
                        "visibility": "buyer_private",
                    }
                ],
            }
        ],
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    summary = run_experiment_config(config_path)

    assert summary.completed == 1
    assert summary.failed == 0


def test_validate_market_accepts_and_rejects_listing_fixtures(tmp_path):
    result = validate_market_dataset(
        products_file="examples/data/scenario_seed_products.json",
        market_comps_file="examples/data/scenario_seed_comps.json",
        active_listings_file=LISTINGS_FIXTURE,
    )
    assert result.status == "passed"
    assert result.active_listing_count == 24

    bad_path = tmp_path / "listings.json"
    bad_path.write_text(
        json.dumps([{"title": "x", "asking_price": -5, "query": "x"}])
    )
    result = validate_market_dataset(
        products_file="examples/data/scenario_seed_products.json",
        market_comps_file="examples/data/scenario_seed_comps.json",
        active_listings_file=bad_path,
    )
    assert result.status == "failed"
    assert any("asking_price" in error for error in result.errors)


def _browse_policy(tmp_path, **overrides):
    path = tmp_path / "policy.json"
    write_market_source_policy(
        path,
        source_id="ebay",
        adapter_kind=overrides.pop("adapter_kind", "ebay_browse"),
        collection_mode=overrides.pop("collection_mode", "official_api"),
        data_rights="official_api_terms",
        terms_url="https://developer.ebay.com/join/api-license-agreement",
        privacy_classification="aggregate_or_user_provided_export",
        live_collection_enabled=overrides.pop("live_collection_enabled", True),
    )
    return path


def _mock_browse_payload(tmp_path):
    payload = {
        "itemSummaries": [
            {
                "title": "Apple iPhone 14 Pro 128GB Unlocked - ships fast",
                "price": {"value": "612.50", "currency": "USD"},
                "condition": "Used",
                "itemCreationDate": "2026-05-25T08:00:00.000Z",
                "shippingOptions": [{"shippingCost": {"value": "11.80"}}],
                "seller": {"feedbackPercentage": "99.6", "username": "secret_user"},
            },
            {
                "title": "iPhone 14 Pro 128GB unlocked, open to offers",
                "price": {"value": "649.00", "currency": "USD"},
                "condition": "Used",
                "itemCreationDate": "2026-04-15T08:00:00.000Z",
                "seller": {"feedbackPercentage": "96.2"},
            },
            {"title": "broken record without price"},
        ]
    }
    path = tmp_path / "browse_response.json"
    path.write_text(json.dumps(payload))
    return path


def test_browse_mock_response_path_normalizes_and_sanitizes(tmp_path):
    policy = _browse_policy(tmp_path)
    mock = _mock_browse_payload(tmp_path)

    records = fetch_ebay_browse_listings(
        query="iphone 14 pro 128gb unlocked",
        source_policy_path=policy,
        mock_response_path=mock,
        as_of="2026-06-10",
    )

    assert len(records) == 2
    first = records[0]
    assert first["asking_price"] == 612.5
    assert first["listing_age_days"] == 16
    assert first["shipping_cost"] == 11.8
    assert first["seller_rating_band"] == "high"
    assert records[1]["seller_rating_band"] == "medium"
    assert all("username" not in json.dumps(record) for record in records)


def test_browse_ingest_writes_tool_ready_fixture(tmp_path):
    policy = _browse_policy(tmp_path)
    mock = _mock_browse_payload(tmp_path)

    result = ingest_ebay_browse_listings(
        query="iphone 14 pro 128gb unlocked",
        source_policy_path=policy,
        snapshot_output=tmp_path / "snapshot.json",
        listings_output=tmp_path / "active_listings.json",
        mock_response_path=mock,
        as_of="2026-06-10",
    )

    assert result.mode == "mock_response"
    assert result.listing_count == 2
    tool = ActiveListingTool.from_json(result.listings_output)
    search = tool.call({"query": "iphone 14 pro 128gb unlocked"}, None)
    assert search["count"] == 2

    snapshot = json.loads((tmp_path / "snapshot.json").read_text())
    assert snapshot["schema_version"] == "opennego.ebay_browse_ingestion.v1"


def test_browse_refuses_without_live_policy(tmp_path):
    mock = _mock_browse_payload(tmp_path)

    offline_policy = _browse_policy(
        tmp_path, collection_mode="official_api", live_collection_enabled=False
    )
    with pytest.raises(MarketSourcePolicyError, match="live_collection_enabled"):
        fetch_ebay_browse_listings(
            query="iphone",
            source_policy_path=offline_policy,
            mock_response_path=mock,
        )

    wrong_adapter = _browse_policy(tmp_path, adapter_kind="ebay_marketplace_insights")
    with pytest.raises(MarketSourcePolicyError, match="adapter_kind"):
        fetch_ebay_browse_listings(
            query="iphone",
            source_policy_path=wrong_adapter,
            mock_response_path=mock,
        )


def test_browse_rejects_empty_results(tmp_path):
    policy = _browse_policy(tmp_path)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"itemSummaries": []}))

    with pytest.raises(EBayBrowseError, match="no active listings"):
        fetch_ebay_browse_listings(
            query="iphone",
            source_policy_path=policy,
            mock_response_path=empty,
        )


def test_cli_ingest_ebay_active_mock_path(tmp_path, capsys):
    policy = _browse_policy(tmp_path)
    mock = _mock_browse_payload(tmp_path)

    code = main(
        [
            "ingest-ebay-active",
            "--query",
            "iphone 14 pro 128gb unlocked",
            "--source-policy",
            str(policy),
            "--snapshot-output",
            str(tmp_path / "snapshot.json"),
            "--listings-output",
            str(tmp_path / "active_listings.json"),
            "--mock-response",
            str(mock),
            "--as-of",
            "2026-06-10",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["listing_count"] == 2
    assert payload["mode"] == "mock_response"
