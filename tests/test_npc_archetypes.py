import json

import pytest

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.agents.profiles import (
    BUYER_POLICIES,
    SELLER_POLICIES,
    ProfileBackedBuyer,
    ProfileBackedSeller,
)
from opennego.environment import NegotiationEnvironment
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH, load_strategy_registry
from opennego.schema import ActionType, Product, Role, Scenario
from opennego.sparring import run_sparring_suite


def _registry():
    return load_strategy_registry(DEFAULT_NPC_REGISTRY_PATH)


def _profile(profile_id):
    registry = _registry()
    for profile in registry.profiles:
        if profile.id == profile_id:
            return profile
    raise AssertionError(f"profile {profile_id} not in registry")


def _scenario(max_turns=8):
    product = Product.from_mapping(
        json.loads(open("examples/data/scenario_seed_products.json").read())[0]
    )
    return Scenario(
        product=product,
        buyer_budget=640.0,
        seller_reservation_price=520.0,
        max_turns=max_turns,
    )


def _run(buyer, seller, max_turns=8):
    env = NegotiationEnvironment(
        scenario=_scenario(max_turns=max_turns), buyer=buyer, seller=seller
    )
    return env.run()


def test_registry_has_tiered_population_with_provenance():
    registry = _registry()
    profiles = registry.profiles

    assert len(profiles) >= 10
    sellers = [profile for profile in profiles if profile.role == Role.SELLER]
    buyers = [profile for profile in profiles if profile.role == Role.BUYER]
    assert len(sellers) >= 7
    assert len(buyers) >= 5
    assert {profile.difficulty for profile in profiles} >= {
        "easy",
        "medium",
        "hard",
        "safety",
    }
    for profile in profiles:
        if profile.metadata.get("source_type") == "curated_npc":
            assert profile.archetype in SELLER_POLICIES or (
                profile.archetype in BUYER_POLICIES
            ) or profile.archetype in {
                "hardline_anchor",
                "evidence_asymmetry",
                "transaction_cost_pressure",
            }


def test_every_new_profile_records_behavior_provenance():
    registry = _registry()
    new_ids = {
        "seller_split_difference_v1",
        "seller_immediate_acceptor_v1",
        "seller_firm_price_v1",
        "seller_lowball_ignorer_v1",
        "seller_deadline_pressurer_v1",
        "seller_precise_counter_v1",
        "seller_scam_offplatform_v1",
        "buyer_split_difference_v1",
        "buyer_lowball_machine_v1",
        "buyer_immediate_acceptor_v1",
        "buyer_ghosting_v1",
        "buyer_scam_overpay_v1",
    }
    found = {profile.id for profile in registry.profiles} & new_ids
    assert found == new_ids
    for profile in registry.profiles:
        if profile.id in new_ids:
            assert profile.metadata.get("behavior_provenance")


def test_split_difference_seller_counters_at_midpoint():
    seller = ProfileBackedSeller(profile=_profile("seller_split_difference_v1"))
    buyer = ProfileBackedBuyer(profile=_profile("buyer_lowball_machine_v1"))

    result = _run(buyer, seller)

    seller_offers = [
        event.offer.price
        for event in result.events
        if event.role == Role.SELLER and event.action_type == ActionType.OFFER
    ]
    buyer_offers = [
        event.offer.price
        for event in result.events
        if event.role == Role.BUYER and event.action_type == ActionType.OFFER
    ]
    assert seller_offers
    first_counter = seller_offers[0]
    expected_anchor = 760.0 * 0.95
    expected = buyer_offers[0] + (expected_anchor - buyer_offers[0]) * 0.5
    assert first_counter == pytest.approx(max(520.0, expected), abs=0.01)


def test_immediate_acceptor_seller_takes_first_reasonable_offer():
    seller = ProfileBackedSeller(profile=_profile("seller_immediate_acceptor_v1"))
    buyer = ToolAwareBuyer()

    result = _run(buyer, seller)

    assert result.outcome == "deal"
    assert result.completed_turns == 2


def test_firm_price_seller_never_concedes():
    seller = ProfileBackedSeller(profile=_profile("seller_firm_price_v1"))
    buyer = ToolAwareBuyer()

    result = _run(buyer, seller)

    seller_offers = [
        event.offer.price
        for event in result.events
        if event.role == Role.SELLER and event.action_type == ActionType.OFFER
    ]
    assert len(set(seller_offers)) == 1
    assert seller_offers[0] == pytest.approx(760.0)
    assert result.outcome == "timeout"


def test_lowball_ignorer_ghosts_below_threshold_and_engages_above():
    profile = _profile("seller_lowball_ignorer_v1")

    lowballer = ProfileBackedBuyer(profile=_profile("buyer_lowball_machine_v1"))
    result = _run(lowballer, ProfileBackedSeller(profile=profile))
    assert result.outcome == "ghosted"

    credible = ToolAwareBuyer()
    result = _run(credible, ProfileBackedSeller(profile=profile))
    assert result.outcome in {"deal", "timeout"}
    assert result.outcome != "ghosted"


def test_deadline_pressurer_walks_after_final_offer():
    seller = ProfileBackedSeller(profile=_profile("seller_deadline_pressurer_v1"))
    buyer = ProfileBackedBuyer(profile=_profile("buyer_lowball_machine_v1"))

    result = _run(buyer, seller, max_turns=12)

    assert result.outcome == "ghosted"
    seller_offers = [
        event
        for event in result.events
        if event.role == Role.SELLER and event.action_type == ActionType.OFFER
    ]
    assert len(seller_offers) == 3


def test_precise_counter_seller_uses_non_round_prices():
    seller = ProfileBackedSeller(profile=_profile("seller_precise_counter_v1"))
    buyer = ProfileBackedBuyer(profile=_profile("buyer_lowball_machine_v1"))

    result = _run(buyer, seller, max_turns=6)

    seller_offers = [
        event.offer.price
        for event in result.events
        if event.role == Role.SELLER and event.action_type == ActionType.OFFER
    ]
    assert seller_offers
    assert all(price != round(price) for price in seller_offers)


def test_scam_seller_baits_below_market_and_accepts_anything():
    seller = ProfileBackedSeller(profile=_profile("seller_scam_offplatform_v1"))
    buyer = ToolAwareBuyer()

    result = _run(buyer, seller)

    opening = next(
        event
        for event in result.events
        if event.role == Role.SELLER and event.action_type == ActionType.OFFER
    )
    assert opening.offer.price < 575.0
    assert "off" in opening.content.lower() or "gift card" in opening.content.lower()
    assert result.outcome == "deal"


def test_scam_buyer_offers_above_asking_with_overpay_story():
    buyer = ProfileBackedBuyer(profile=_profile("buyer_scam_overpay_v1"))
    seller = ScriptedSeller()

    result = _run(buyer, seller)

    opening = next(
        event
        for event in result.events
        if event.role == Role.BUYER and event.action_type == ActionType.OFFER
    )
    assert opening.offer.price > 760.0
    assert "overpay" in opening.content.lower() or "refund" in opening.content.lower()
    assert result.outcome == "deal"


def test_ghosting_buyer_disappears_after_high_counters():
    buyer = ProfileBackedBuyer(profile=_profile("buyer_ghosting_v1"))
    seller = ProfileBackedSeller(profile=_profile("seller_firm_price_v1"))

    result = _run(buyer, seller, max_turns=12)

    assert result.outcome == "ghosted"
    assert result.events[-1].role == Role.BUYER


def test_immediate_acceptor_buyer_takes_at_market_price():
    buyer = ProfileBackedBuyer(profile=_profile("buyer_immediate_acceptor_v1"))
    seller = ProfileBackedSeller(profile=_profile("seller_immediate_acceptor_v1"))

    result = _run(buyer, seller)

    assert result.outcome == "deal"
    assert result.completed_turns <= 3


def test_full_seller_roster_sparring_completes(tmp_path):
    summary = run_sparring_suite(
        output_dir=tmp_path / "sparring",
        user_role=Role.BUYER,
        fail_fast=False,
    )

    assert summary.total_profiles >= 7
    assert summary.completed == summary.total_profiles
    assert summary.failed == 0
