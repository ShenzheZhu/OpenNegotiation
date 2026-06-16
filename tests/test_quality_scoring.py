"""Quality-aware match scoring: the lemon has to bite (#200)."""

from opennego.rating import compute_match_score


def _score(deal_price, *, true_quality=None, claimed_quality=None, **kw):
    return compute_match_score(
        outcome="deal",
        deal_price=deal_price,
        buyer_budget=600.0,
        seller_reservation=300.0,
        market_reference=None,
        true_quality=true_quality,
        claimed_quality=claimed_quality,
        **kw,
    )


def test_omitting_quality_is_identical_to_headline_price():
    bare = _score(500.0)
    with_equal = _score(500.0, true_quality=0.9, claimed_quality=0.9)
    # true == claimed -> quality_ratio 1.0 -> no change.
    assert bare == with_equal


def test_only_one_quality_arg_is_a_no_op():
    bare = _score(500.0)
    assert _score(500.0, true_quality=0.4) == bare
    assert _score(500.0, claimed_quality=0.9) == bare


def test_lemon_tanks_the_face_value_buyer():
    # Item claimed "like new" (0.9) is really a lemon (0.45): realized value is
    # half the budget, so paying 500 wipes out the buyer's surplus.
    healthy = _score(500.0).buyer
    lemon = _score(500.0, true_quality=0.45, claimed_quality=0.9).buyer
    assert lemon < healthy
    # Realized value 300 < price 500 -> surplus floors at 0, only the market
    # term remains.
    assert lemon < 0.25


def test_inspecting_buyer_beats_face_value_buyer():
    # Same lemon. The buyer who inspected and negotiated down to 250 keeps
    # surplus; the one who paid the claim price (500) does not.
    inspected = _score(250.0, true_quality=0.45, claimed_quality=0.9).buyer
    face_value = _score(500.0, true_quality=0.45, claimed_quality=0.9).buyer
    assert inspected > face_value


def test_seller_penalized_only_when_buyer_overpays_vs_true_value():
    # Sold the lemon at a high price the buyer overpaid for -> dispute exposure.
    exploited = _score(500.0, true_quality=0.45, claimed_quality=0.9).seller
    headline = _score(500.0).seller
    assert exploited < headline

    # Same lemon sold at/below its realized value (300) -> the buyer did not
    # overpay, so the seller carries no penalty relative to that price.
    fair = compute_match_score(
        outcome="deal",
        deal_price=290.0,
        buyer_budget=600.0,
        seller_reservation=250.0,
        market_reference=None,
        true_quality=0.45,
        claimed_quality=0.9,
    ).seller
    fair_headline = compute_match_score(
        outcome="deal",
        deal_price=290.0,
        buyer_budget=600.0,
        seller_reservation=250.0,
        market_reference=None,
    ).seller
    assert fair == fair_headline


def test_understatement_is_not_rewarded():
    # A buyer cannot benefit from the item being better than claimed: ratio is
    # capped at 1.0, so the score matches the as-described case.
    better = _score(450.0, true_quality=1.0, claimed_quality=0.6)
    as_described = _score(450.0, true_quality=0.6, claimed_quality=0.6)
    assert better == as_described


def test_non_deal_outcomes_ignore_quality():
    rejected = compute_match_score(
        outcome="rejected",
        deal_price=None,
        buyer_budget=600.0,
        seller_reservation=300.0,
        market_reference=None,
        true_quality=0.1,
        claimed_quality=0.9,
    )
    assert rejected.buyer == rejected.seller  # flat no-deal score, unaffected
