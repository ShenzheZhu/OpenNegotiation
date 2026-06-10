import json

import pytest

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import to_jsonable
from opennego.environment import NegotiationEnvironment
from opennego.scenario_generator import (
    BATNA_SCHEMA_VERSION,
    GeneratorSettings,
    ScenarioGenerationError,
    generate_scenarios,
    load_products,
)
from opennego.schema import Role

PRODUCTS_FILE = "examples/data/real_market_products.json"


def _products():
    return load_products(PRODUCTS_FILE)


def test_same_seed_reproduces_identical_records():
    first = generate_scenarios(_products(), seed=13, scenarios_per_product=3)
    second = generate_scenarios(_products(), seed=13, scenarios_per_product=3)

    assert json.dumps(to_jsonable(first), sort_keys=True) == json.dumps(
        to_jsonable(second), sort_keys=True
    )


def test_different_seeds_change_constraints():
    first = generate_scenarios(_products(), seed=13)[0]
    second = generate_scenarios(_products(), seed=14)[0]

    assert (first.buyer_budget, first.seller_reservation_price) != (
        second.buyer_budget,
        second.seller_reservation_price,
    )


def test_batna_derivation_recorded_and_bounds_valid():
    settings = GeneratorSettings()
    scenarios = generate_scenarios(
        _products(), seed=7, scenarios_per_product=5, settings=settings
    )

    for scenario in scenarios:
        batna = scenario.metadata["batna"]
        buyer = batna["buyer"]
        seller = batna["seller"]
        reference = scenario.product.market_reference

        assert batna["schema_version"] == BATNA_SCHEMA_VERSION
        assert scenario.buyer_budget == pytest.approx(
            buyer["alternative_price"] + buyer["switching_friction"]
        )
        assert scenario.buyer_budget == buyer["derived_budget"]
        assert scenario.seller_reservation_price == seller["derived_reservation"]
        assert scenario.seller_reservation_price >= seller["reservation_floor"]
        assert scenario.seller_reservation_price > 0
        assert scenario.buyer_budget > 0
        assert reference.p25_price <= buyer["alternative_price"] <= reference.p75_price
        assert seller["expected_resale_price"] <= reference.reference_price
        assert batna["source"]["reference_price"] == reference.reference_price


def test_scenarios_per_product_yields_distinct_scenarios():
    scenarios = generate_scenarios(_products(), seed=21, scenarios_per_product=4)

    ids = {scenario.metadata["scenario_id"] for scenario in scenarios}
    budgets = {scenario.buyer_budget for scenario in scenarios}
    assert len(ids) == 4
    assert len(budgets) > 1


def test_requires_market_reference():
    products = load_products("examples/data/products.json")

    with pytest.raises(ScenarioGenerationError, match="camera_001"):
        generate_scenarios(products, seed=13)


def test_environment_exposes_own_side_outside_option_only():
    scenario = generate_scenarios(_products(), seed=13)[0]
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
    )

    buyer_state = env._context_for(Role.BUYER).private_state
    seller_state = env._context_for(Role.SELLER).private_state

    assert buyer_state["outside_option"]["basis"] == "next_best_active_listing"
    assert "alternative_price" in buyer_state["outside_option"]
    assert "derived_reservation" not in buyer_state["outside_option"]
    assert seller_state["outside_option"]["basis"] == "relist_and_wait"
    assert "derived_budget" not in seller_state["outside_option"]
    assert "alternative_price" not in seller_state["outside_option"]


def test_environment_without_batna_metadata_unchanged():
    products = load_products("examples/data/products.json")
    from opennego.schema import Scenario

    scenario = Scenario(
        product=products[0],
        buyer_budget=850.0,
        seller_reservation_price=620.0,
    )
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
    )

    assert "outside_option" not in env._context_for(Role.BUYER).private_state
    assert "outside_option" not in env._context_for(Role.SELLER).private_state


def test_generated_scenarios_run_to_completion():
    scenario = generate_scenarios(_products(), seed=13)[0]
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
    )

    result = env.run()

    assert result.outcome in {"deal", "rejected", "timeout"}
    if result.outcome == "deal":
        assert result.deal_price <= scenario.buyer_budget
        assert result.deal_price >= scenario.seller_reservation_price
