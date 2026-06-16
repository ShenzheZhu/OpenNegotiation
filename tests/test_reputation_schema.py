"""Reputation schema + shared band/risk module (#209)."""

import json

import pytest

from opennego.artifacts import ScenarioArtifact, to_jsonable
from opennego.reputation import (
    band_from_feedback_pct,
    normalize_band,
    reputation_risk,
)
from opennego.scenario_generator import generate_scenarios, load_products
from opennego.schema import Product, Role, Scenario, SellerReputation


# --- shared module ---------------------------------------------------------


@pytest.mark.parametrize(
    "band,expected",
    [("high", 0.0), ("medium", 0.06), ("low", 0.18), ("unknown", 0.10)],
)
def test_reputation_risk_weights(band, expected):
    assert reputation_risk(band) == expected


def test_reputation_risk_defaults_unknown():
    assert reputation_risk(None) == 0.10
    assert reputation_risk("nonsense") == 0.10
    assert reputation_risk("HIGH") == 0.0  # case-insensitive


@pytest.mark.parametrize(
    "pct,band",
    [(99.5, "high"), (99.0, "high"), (96.0, "medium"), (95.0, "medium"), (90.0, "low"), (None, "unknown")],
)
def test_band_from_feedback_pct(pct, band):
    assert band_from_feedback_pct(pct) == band


def test_normalize_band():
    assert normalize_band("Low") == "low"
    assert normalize_band("bogus") == "unknown"
    assert normalize_band(None) == "unknown"


# --- selection drill still uses the shared map -----------------------------


def test_selection_drill_imports_shared_risk_map():
    from opennego import skill_drills

    assert not hasattr(skill_drills, "_RATING_RISK")
    assert skill_drills.reputation_risk("low") == 0.18


# --- SellerReputation type -------------------------------------------------


def test_seller_reputation_from_mapping_derives_band():
    rep = SellerReputation.from_mapping({"feedback_pct": 96.5, "feedback_count": 1200})
    assert rep.band == "medium"
    assert rep.feedback_pct == 96.5
    assert rep.feedback_count == 1200


def test_seller_reputation_explicit_band_wins():
    rep = SellerReputation.from_mapping({"band": "high", "feedback_pct": 80.0})
    assert rep.band == "high"


# --- scenario field is public + additive -----------------------------------


def _scenario(**kw):
    product = load_products("examples/data/real_market_products.json")[0]
    return Scenario(
        product=product,
        buyer_budget=700.0,
        seller_reservation_price=520.0,
        max_turns=6,
        **kw,
    )


def test_seller_reputation_defaults_none_and_is_visible_to_both_roles():
    from opennego.agents import ScriptedSeller, ToolAwareBuyer
    from opennego.environment import NegotiationEnvironment

    assert _scenario().seller_reputation is None
    rep = SellerReputation(band="low", feedback_pct=92.0)
    env = NegotiationEnvironment(
        scenario=_scenario(seller_reputation=rep),
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
    )
    # Public: both roles see it through the scenario.
    assert env._context_for(Role.BUYER).scenario.seller_reputation.band == "low"
    assert env._context_for(Role.SELLER).scenario.seller_reputation.band == "low"


def test_scenario_artifact_round_trips_reputation():
    rep = SellerReputation(band="medium", feedback_pct=97.0, feedback_count=500, source="fixture")
    artifact = ScenarioArtifact.from_scenario(_scenario(seller_reputation=rep), scenario_id="s1")
    restored = ScenarioArtifact.from_mapping(json.loads(json.dumps(to_jsonable(artifact))))
    assert restored.seller_reputation.band == "medium"
    assert restored.seller_reputation.feedback_count == 500
    assert restored.to_scenario().seller_reputation.feedback_pct == 97.0


# --- generator wiring ------------------------------------------------------


def test_generator_carries_product_reputation():
    products = load_products("examples/data/real_market_products.json")
    base = products[0]
    product = Product(
        id=base.id,
        name=base.name,
        description=base.description,
        list_price=base.list_price,
        wholesale_price=base.wholesale_price,
        condition=base.condition,
        market_reference=base.market_reference,
        attributes={"seller_reputation": {"band": "low", "feedback_pct": 91.0}},
    )
    scenarios = generate_scenarios([product], seed=5)
    assert scenarios[0].seller_reputation is not None
    assert scenarios[0].seller_reputation.band == "low"


def test_generator_without_reputation_is_additive():
    products = load_products("examples/data/real_market_products.json")
    scenarios = generate_scenarios(products, seed=5)
    # Stock fixtures carry no reputation attribute -> None, unchanged behavior.
    assert all(s.seller_reputation is None for s in scenarios)
