import json

import pytest

from opennego.artifacts import to_jsonable
from opennego.market import (
    MARKET_STATE_SCHEMA_VERSION,
    MarketError,
    build_market,
    mark_sold,
    market_state_from_mapping,
    step_market,
)

PRODUCTS = "examples/data/scenario_seed_products.json"


def test_build_market_is_deterministic():
    a = build_market(PRODUCTS, seed=7, listings_per_product=2)
    b = build_market(PRODUCTS, seed=7, listings_per_product=2)
    assert [l.asking_price for l in a.listings] == [l.asking_price for l in b.listings]
    assert a.schema_version == MARKET_STATE_SCHEMA_VERSION
    assert len(a.listings) == len(json.loads(open(PRODUCTS).read())) * 2


def test_discover_ranks_best_apparent_deal_first():
    state = build_market(PRODUCTS, seed=7, listings_per_product=3)
    cards = state.discover(limit=5)
    spreads = [c["spread_vs_reference"] for c in cards]
    assert spreads == sorted(spreads, reverse=True)
    assert all("asking_price" in c for c in cards)


def test_discover_filters_by_category_and_price():
    state = build_market(PRODUCTS, seed=7, listings_per_product=2)
    cameras = state.discover(category="cameras")
    assert cameras
    assert all(c["category"] == "cameras" for c in cameras)
    cheap = state.discover(max_price=400.0)
    assert all(c["asking_price"] <= 400.0 for c in cheap)


def test_step_ages_and_drops_stale_prices():
    state = build_market(PRODUCTS, seed=7, listings_per_product=2, drop_after=2)
    first = state.active()[0]
    advanced = state
    for _ in range(4):
        advanced = step_market(advanced)
    assert advanced.period == 4
    same = next(l for l in advanced.listings if l.listing_id == first.listing_id)
    # Aged, and if it was over-reference it should have dropped.
    assert same.age_periods > first.age_periods
    if first.asking_price > first.reference_price:
        assert same.asking_price <= first.asking_price


def test_step_expires_and_relists_deterministically():
    a = build_market(PRODUCTS, seed=3, listings_per_product=2, max_age=2)
    b = build_market(PRODUCTS, seed=3, listings_per_product=2, max_age=2)
    for _ in range(5):
        a = step_market(a)
        b = step_market(b)
    assert [l.listing_id for l in a.listings] == [l.listing_id for l in b.listings]
    assert any(l.status == "expired" for l in a.listings)
    # Relisted listings keep the market populated.
    assert a.active()


def test_mark_sold_removes_from_discovery():
    state = build_market(PRODUCTS, seed=7, listings_per_product=2)
    target = state.active()[0]
    sold = mark_sold(state, target.listing_id)
    ids = {c["listing_id"] for c in sold.discover(limit=99)}
    assert target.listing_id not in ids
    with pytest.raises(MarketError, match="mark sold"):
        mark_sold(sold, target.listing_id)


def test_market_state_round_trips_through_json():
    state = build_market(PRODUCTS, seed=7, listings_per_product=2)
    state = step_market(state)
    restored = market_state_from_mapping(json.loads(json.dumps(to_jsonable(state))))
    assert restored.period == state.period
    assert [l.listing_id for l in restored.listings] == [
        l.listing_id for l in state.listings
    ]


def test_build_rejects_empty_and_bad_inputs(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    with pytest.raises(MarketError, match="non-empty"):
        build_market(empty)
    with pytest.raises(MarketError, match="listings_per_product"):
        build_market(PRODUCTS, listings_per_product=0)
