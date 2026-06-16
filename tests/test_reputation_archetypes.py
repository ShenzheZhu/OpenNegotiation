"""Reputation NPC archetypes (#211)."""

import json

from opennego.agents import ScriptedSeller
from opennego.agents.profiles import (
    BUYER_POLICIES,
    SELLER_POLICIES,
    ProfileBackedBuyer,
    ProfileBackedSeller,
)
from opennego.environment import NegotiationEnvironment
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH, load_strategy_registry
from opennego.schema import ActionType, Product, Role, Scenario, SellerReputation


def _registry():
    return load_strategy_registry(DEFAULT_NPC_REGISTRY_PATH)


def _profile(profile_id):
    for profile in _registry().profiles:
        if profile.id == profile_id:
            return profile
    raise AssertionError(f"profile {profile_id} not in registry")


def _product():
    base = json.loads(open("examples/data/scenario_seed_products.json").read())[0]
    return Product.from_mapping(base)


def _scenario(band):
    return Scenario(
        product=_product(),
        buyer_budget=900.0,
        seller_reservation_price=300.0,
        max_turns=8,
        seller_reputation=SellerReputation(band=band) if band else None,
    )


def _seller_offers(events):
    return [
        e.offer.price
        for e in events
        if e.role == Role.SELLER and e.action_type == ActionType.OFFER and e.offer
    ]


def _buyer_offers(events):
    return [
        e.offer.price
        for e in events
        if e.role == Role.BUYER and e.action_type == ActionType.OFFER and e.offer
    ]


class _SilentBuyer:
    name = "silent_buyer"
    role = Role.BUYER

    def act(self, context):
        from opennego.schema import AgentAction

        return AgentAction.message("waiting")


def test_new_archetypes_registered_with_provenance():
    assert "reputation_premium_seller" in SELLER_POLICIES
    assert "reputation_discount_buyer" in BUYER_POLICIES
    for pid in ("seller_reputation_premium_v1", "buyer_reputation_discount_v1"):
        assert _profile(pid).metadata.get("behavior_provenance")


def test_reputation_discount_buyer_offers_less_to_low_rep_seller():
    def first_offer(band):
        buyer = ProfileBackedBuyer(profile=_profile("buyer_reputation_discount_v1"))
        env = NegotiationEnvironment(
            scenario=_scenario(band), buyer=buyer, seller=ScriptedSeller()
        )
        return _buyer_offers(env.run().events)[0]

    assert first_offer("low") < first_offer("high")


def test_reputation_premium_seller_anchors_higher_than_baseline():
    scenario = _scenario("high")
    premium = ProfileBackedSeller(profile=_profile("seller_reputation_premium_v1"))
    premium_open = _seller_offers(
        NegotiationEnvironment(
            scenario=scenario, buyer=_SilentBuyer(), seller=premium
        ).run().events
    )[0]
    baseline = ProfileBackedSeller(profile=_profile("seller_split_difference_v1"))
    baseline_open = _seller_offers(
        NegotiationEnvironment(
            scenario=scenario, buyer=_SilentBuyer(), seller=baseline
        ).run().events
    )[0]
    assert premium_open > baseline_open


def test_premium_seller_cites_reputation():
    scenario = _scenario("high")
    premium = ProfileBackedSeller(profile=_profile("seller_reputation_premium_v1"))
    messages = " ".join(
        e.content
        for e in NegotiationEnvironment(
            scenario=scenario, buyer=_SilentBuyer(), seller=premium
        ).run().events
        if e.role == Role.SELLER
    ).lower()
    assert "top-rated" in messages or "reputation" in messages or "protection" in messages


def test_reputation_discount_buyer_is_additive_without_reputation():
    # No reputation on the scenario -> behaves like a normal buyer (no crash,
    # offers something).
    buyer = ProfileBackedBuyer(profile=_profile("buyer_reputation_discount_v1"))
    env = NegotiationEnvironment(
        scenario=_scenario(None), buyer=buyer, seller=ScriptedSeller()
    )
    assert _buyer_offers(env.run().events)
