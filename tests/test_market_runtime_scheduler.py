import json

import pytest

from opennego.cli import main
from opennego.market import build_market
from opennego.market_runtime import (
    MARKET_EPISODE_SCHEMA_VERSION,
    MarketRuntimeError,
    run_market_episode,
)
from opennego.rating import RatingStore
from opennego.schema import Role

PRODUCTS = "examples/data/scenario_seed_products.json"


def _market(seed=7):
    return build_market(PRODUCTS, seed=seed, listings_per_product=2)


def test_episode_runs_concurrent_threads():
    state = _market()
    result = run_market_episode(
        state, buyer_ids=["buyer_a", "buyer_b"], shortlist_size=3, seed=7
    )
    assert result.schema_version == MARKET_EPISODE_SCHEMA_VERSION
    assert result.thread_count == 2 * 3
    assert result.buyer_count == 2
    # Every thread ends resolved (no thread left open).
    assert all(
        t["status"] in {"deal", "rejected", "timeout", "ghosted", "cancelled"}
        for t in result.threads
    )


def test_clearing_closes_conflicting_threads():
    state = _market()
    result = run_market_episode(
        state, buyer_ids=["buyer_a", "buyer_b"], shortlist_size=3, seed=7
    )
    # A listing can be sold to at most one buyer.
    sold_listings = [
        t["listing_id"] for t in result.threads if t["status"] == "deal"
    ]
    assert len(sold_listings) == len(set(sold_listings))
    # A buyer commits to at most one deal.
    for buyer in ("buyer_a", "buyer_b"):
        buyer_deals = [
            t for t in result.threads
            if t["buyer_id"] == buyer and t["status"] == "deal"
        ]
        assert len(buyer_deals) <= 1
    # Clearings reference cancellations consistent with the deals.
    if result.clearings:
        assert result.deals >= 1


def test_episode_is_deterministic():
    a = run_market_episode(_market(), buyer_ids=["x", "y"], seed=7)
    b = run_market_episode(_market(), buyer_ids=["x", "y"], seed=7)
    assert [t["status"] for t in a.threads] == [t["status"] for t in b.threads]
    assert [t["deal_price"] for t in a.threads] == [t["deal_price"] for t in b.threads]


def test_episode_ingests_into_rating_store_idempotently():
    store = RatingStore()
    run_market_episode(_market(), buyer_ids=["buyer_a", "buyer_b"], seed=7,
                       store=store, episode_id="ep1")
    first = store.match_count()
    assert first >= 1
    # Re-running the same episode id does not double-count.
    run_market_episode(_market(), buyer_ids=["buyer_a", "buyer_b"], seed=7,
                       store=store, episode_id="ep1")
    assert store.match_count() == first
    # A buyer that closed a deal is rated on the buyer track.
    assert store.ratings_for_role(Role.BUYER)


def test_empty_buyers_or_market_raise(tmp_path):
    with pytest.raises(MarketRuntimeError, match="buyer_ids"):
        run_market_episode(_market(), buyer_ids=[])


def test_market_run_cli(tmp_path, capsys):
    out = tmp_path / "episode.json"
    code = main(
        [
            "market-run",
            "--products-file", PRODUCTS,
            "--seed", "7",
            "--buyer", "buyer_a",
            "--buyer", "buyer_b",
            "--output", str(out),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["schema_version"] == MARKET_EPISODE_SCHEMA_VERSION
    assert out.exists()
