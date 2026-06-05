import pytest

from opennego.metrics import compute_metrics
from opennego.schema import Product, Scenario


def test_market_style_product_can_omit_observed_cost():
    product = Product.from_mapping(
        {
            "id": "iphone_14_pro_128gb_unlocked_good",
            "name": "Apple iPhone 14 Pro 128GB Unlocked",
            "description": "Used unlocked phone with light wear.",
            "condition": "used_good",
            "asking_price": 610.0,
            "synthetic_seller_reservation_price": 520.0,
            "market_reference": {
                "reference_price": 575.0,
                "p25_price": 540.0,
                "p75_price": 610.0,
                "sample_size": 24,
                "currency": "USD",
                "window_days": 90,
                "source": "fixture_sold_comps",
            },
        }
    )

    assert product.list_price == 610.0
    assert product.wholesale_price == 520.0
    assert product.market_reference is not None
    assert product.market_reference.reference_price == 575.0
    assert product.market_reference.iqr == 70.0
    assert product.attributes["legacy_wholesale_basis"] == "synthetic_seller_reservation_price"


def test_market_reference_metrics_measure_gap_to_sold_distribution():
    product = Product.from_mapping(
        {
            "id": "iphone_14_pro_128gb_unlocked_good",
            "name": "Apple iPhone 14 Pro 128GB Unlocked",
            "description": "Used unlocked phone with light wear.",
            "condition": "used_good",
            "asking_price": 610.0,
            "synthetic_seller_reservation_price": 520.0,
            "market_reference": {
                "reference_price": 575.0,
                "p25_price": 540.0,
                "p75_price": 610.0,
            },
        }
    )
    scenario = Scenario(
        product=product,
        buyer_budget=640.0,
        seller_reservation_price=520.0,
        max_turns=8,
    )

    metrics = compute_metrics(
        scenario=scenario,
        outcome="deal",
        deal_price=560.0,
        events=[],
    )

    assert metrics["market_reference_price"] == 575.0
    assert metrics["market_price_gap"] == 15.0
    assert metrics["normalized_market_gap"] == pytest.approx(15.0 / 70.0)
    assert metrics["buyer_savings_vs_market_reference"] == 15.0
    assert metrics["seller_revenue_vs_market_reference"] == -15.0
