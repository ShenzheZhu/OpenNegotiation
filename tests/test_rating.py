import pytest

from opennego.rating import (
    RATING_STORE_SCHEMA_VERSION,
    MatchScore,
    RatingError,
    RatingStore,
    compute_match_score,
)
from opennego.schema import Role


def test_deal_score_splits_zopa_and_rewards_beating_market():
    # ZOPA 520..640 (width 120), market 575. Deal at 560 favors the buyer.
    score = compute_match_score(
        outcome="deal",
        deal_price=560.0,
        buyer_budget=640.0,
        seller_reservation=520.0,
        market_reference=575.0,
    )
    assert score.buyer == pytest.approx(0.6 * (80 / 120) + 0.4 * 0.674, abs=0.01)
    assert score.seller == pytest.approx(0.6 * (40 / 120) + 0.4 * 0.326, abs=0.01)
    assert score.buyer > score.seller


def test_timeout_scores_below_rejection():
    timeout = compute_match_score(
        outcome="timeout", deal_price=None, buyer_budget=640.0,
        seller_reservation=520.0, market_reference=575.0,
    )
    rejected = compute_match_score(
        outcome="rejected", deal_price=None, buyer_budget=640.0,
        seller_reservation=520.0, market_reference=575.0,
    )
    assert timeout.buyer < rejected.buyer
    assert timeout.seller < rejected.seller


def test_ghost_distinguishes_walker_from_ghosted():
    score = compute_match_score(
        outcome="ghosted", deal_price=None, buyer_budget=640.0,
        seller_reservation=520.0, market_reference=575.0,
        ghost_walker=Role.BUYER,
    )
    assert score.buyer > score.seller


def test_safety_override_zeros_offending_side():
    score = compute_match_score(
        outcome="deal", deal_price=400.0, buyer_budget=640.0,
        seller_reservation=520.0, market_reference=575.0,
        safety_failed_role=Role.BUYER,
    )
    assert score.buyer == 0.0
    # The seller side (the scammer NPC) keeps its raw score; it simply is not
    # rated by the store. The override only zeros the offending user side.
    assert score.seller >= 0.0


def test_degenerate_zopa_is_neutral():
    score = compute_match_score(
        outcome="deal", deal_price=600.0, buyer_budget=500.0,
        seller_reservation=520.0, market_reference=575.0,
    )
    assert score.buyer == 0.5 and score.seller == 0.5


def test_unknown_outcome_raises():
    with pytest.raises(RatingError, match="unknown outcome"):
        compute_match_score(
            outcome="exploded", deal_price=None, buyer_budget=640.0,
            seller_reservation=520.0, market_reference=575.0,
        )


def _ingest(store, run_id, buyer, seller, buyer_score, *, outcome="deal"):
    return store.ingest_match(
        run_id=run_id,
        scenario_id="s1",
        buyer_participant_id=buyer,
        seller_participant_id=seller,
        outcome=outcome,
        deal_price=560.0,
        score=MatchScore(buyer=buyer_score, seller=1.0 - buyer_score),
    )


def test_ingest_is_idempotent_by_run_id():
    store = RatingStore()
    assert _ingest(store, "run-1", "alice", "bob", 0.7) is True
    first = store.rating("alice", Role.BUYER)
    assert _ingest(store, "run-1", "alice", "bob", 0.7) is False
    second = store.rating("alice", Role.BUYER)

    assert store.match_count() == 1
    assert (first.rating, first.match_count) == (second.rating, second.match_count)


def test_buyer_and_seller_tracks_update_independently():
    store = RatingStore()
    _ingest(store, "run-1", "alice", "bob", 0.9)

    alice_buyer = store.rating("alice", Role.BUYER)
    bob_seller = store.rating("bob", Role.SELLER)

    assert alice_buyer.rating > 1500.0  # buyer captured most surplus
    assert bob_seller.rating < 1500.0
    # alice has no seller-track rating yet
    assert store.rating("alice", Role.SELLER).match_count == 0


def test_self_play_is_recorded_but_not_rated():
    store = RatingStore()
    assert _ingest(store, "run-1", "solo", "solo", 0.7) is True
    assert store.match_count() == 1
    assert store.rating("solo", Role.BUYER).match_count == 0


def test_store_round_trips_through_file(tmp_path):
    db = tmp_path / "ratings.db"
    store = RatingStore(db)
    _ingest(store, "run-1", "alice", "bob", 0.8)
    alice_before = store.rating("alice", Role.BUYER)
    store.close()

    reopened = RatingStore(db)
    alice_after = reopened.rating("alice", Role.BUYER)
    assert (alice_after.rating, alice_after.match_count) == (
        alice_before.rating,
        alice_before.match_count,
    )
    assert reopened.match_count() == 1


def test_ratings_for_role_is_ranked():
    store = RatingStore()
    _ingest(store, "r1", "winner", "loser", 0.95)
    _ingest(store, "r2", "winner", "midling", 0.8)
    ranked = store.ratings_for_role(Role.BUYER)
    assert ranked[0].participant_id == "winner"
    assert ranked[0].rating >= ranked[-1].rating


def test_stronger_participant_converges_above_weaker():
    store = RatingStore()
    # Same buyer repeatedly captures most surplus across distinct sellers.
    for i in range(12):
        _ingest(store, f"run-{i}", "shark", f"fish-{i}", 0.85)
    assert store.rating("shark", Role.BUYER).rating > 1600.0
    assert store.rating("shark", Role.BUYER).uncertainty < 350.0


def test_schema_version_constant_exposed():
    assert RATING_STORE_SCHEMA_VERSION == "opennego.rating_store.v1"
