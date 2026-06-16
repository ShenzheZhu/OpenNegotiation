"""Reputation-aware match scoring (#210)."""

from opennego.rating import compute_match_score


def _score(deal_price, *, reputation_band=None, **kw):
    return compute_match_score(
        outcome="deal",
        deal_price=deal_price,
        buyer_budget=600.0,
        seller_reservation=300.0,
        market_reference=None,
        reputation_band=reputation_band,
        **kw,
    )


def test_omitting_band_or_high_is_identical_to_today():
    bare = _score(450.0)
    assert _score(450.0, reputation_band="high") == bare


def test_low_reputation_lowers_buyer_surplus_at_same_price():
    high = _score(450.0, reputation_band="high").buyer
    low = _score(450.0, reputation_band="low").buyer
    medium = _score(450.0, reputation_band="medium").buyer
    assert low < medium < high


def test_low_reputation_penalizes_seller_for_buyer_overpay():
    # Realized value drops with reputation, so the same price becomes an
    # overpay the seller is penalized for.
    high = _score(540.0, reputation_band="high").seller
    low = _score(540.0, reputation_band="low").seller
    assert low < high


def test_reputation_stacks_with_quality():
    # At a price where the lemon still leaves the buyer positive surplus, the
    # extra reputation haircut erodes it further.
    lemon_only = _score(360.0, true_quality=0.6, claimed_quality=0.9).buyer
    lemon_low_rep = _score(
        360.0, true_quality=0.6, claimed_quality=0.9, reputation_band="low"
    ).buyer
    assert lemon_low_rep < lemon_only


def test_unknown_band_applies_a_haircut():
    high = _score(450.0, reputation_band="high").buyer
    unknown = _score(450.0, reputation_band="unknown").buyer
    assert unknown < high


def test_non_deal_outcome_ignores_reputation():
    rejected = compute_match_score(
        outcome="rejected",
        deal_price=None,
        buyer_budget=600.0,
        seller_reservation=300.0,
        market_reference=None,
        reputation_band="low",
    )
    assert rejected.buyer == rejected.seller
