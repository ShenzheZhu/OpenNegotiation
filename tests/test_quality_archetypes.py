"""Quality-aware NPC archetypes (#202)."""

import json

from opennego.agents import ScriptedSeller
from opennego.agents.profiles import (
    BUYER_POLICIES,
    SELLER_POLICIES,
    ProfileBackedBuyer,
    ProfileBackedSeller,
)
from opennego.environment import NegotiationEnvironment, ToolRuntimeConfig
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH, load_strategy_registry
from opennego.schema import ActionType, Product, Role, Scenario
from opennego.tools import QualityInspectionTool


def _registry():
    return load_strategy_registry(DEFAULT_NPC_REGISTRY_PATH)


def _profile(profile_id):
    for profile in _registry().profiles:
        if profile.id == profile_id:
            return profile
    raise AssertionError(f"profile {profile_id} not in registry")


def _product(condition="Used - Like New"):
    base = json.loads(open("examples/data/scenario_seed_products.json").read())[0]
    base = dict(base)
    base["condition"] = condition
    return Product.from_mapping(base)


def _scenario(**kw):
    return Scenario(
        product=_product(kw.pop("condition", "Used - Like New")),
        buyer_budget=kw.pop("buyer_budget", 900.0),
        seller_reservation_price=kw.pop("seller_reservation_price", 200.0),
        max_turns=kw.pop("max_turns", 8),
        **kw,
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


def _inspect_tool(scenario):
    return (
        (QualityInspectionTool.from_scenario(scenario, base_seed=4),),
        (ToolRuntimeConfig(name="inspect", roles=(Role.BUYER,), visibility="private"),),
    )


# --- registry --------------------------------------------------------------


def test_new_archetypes_registered():
    assert "honest_discloser" in SELLER_POLICIES
    assert "quality_overstater" in SELLER_POLICIES
    assert "quality_skeptic" in BUYER_POLICIES
    ids = {p.id for p in _registry().profiles}
    assert {
        "seller_honest_discloser_v1",
        "seller_quality_overstater_v1",
        "buyer_quality_skeptic_v1",
    } <= ids


def test_new_profiles_record_provenance():
    for pid in (
        "seller_honest_discloser_v1",
        "seller_quality_overstater_v1",
        "buyer_quality_skeptic_v1",
    ):
        assert _profile(pid).metadata.get("behavior_provenance")


# --- honest discloser ------------------------------------------------------


def test_honest_discloser_states_true_condition_and_prices_it_in():
    scenario = _scenario(
        seller_true_condition="screen has a faint scratch under the bezel",
        seller_true_quality=0.4,
    )
    honest = ProfileBackedSeller(profile=_profile("seller_honest_discloser_v1"))
    env = NegotiationEnvironment(
        scenario=scenario, buyer=_silent_buyer(), seller=honest
    )
    result = env.run()
    seller_messages = " ".join(
        e.content for e in result.events if e.role == Role.SELLER
    )
    assert "faint scratch" in seller_messages

    # The honest opening prices the disclosed defect in, below a non-disclosing
    # hardline anchor on the same lemon.
    honest_open = _seller_offers(result.events)[0]
    hardline = ProfileBackedSeller(profile=_profile("seller_hardline_anchor_v1"))
    hard_env = NegotiationEnvironment(
        scenario=scenario, buyer=_silent_buyer(), seller=hardline
    )
    hard_open = _seller_offers(hard_env.run().events)[0]
    assert honest_open < hard_open


# --- quality overstater ----------------------------------------------------


def test_quality_overstater_never_discloses_and_anchors_high():
    scenario = _scenario(
        seller_true_condition="battery is swollen",
        seller_true_quality=0.4,
    )
    seller = ProfileBackedSeller(profile=_profile("seller_quality_overstater_v1"))
    env = NegotiationEnvironment(
        scenario=scenario, buyer=_silent_buyer(), seller=seller
    )
    result = env.run()
    seller_messages = " ".join(
        e.content for e in result.events if e.role == Role.SELLER
    )
    assert "swollen" not in seller_messages
    assert "mint" in seller_messages.lower() or "flawless" in seller_messages.lower()
    # Anchors near list, not marked down for the hidden defect.
    assert _seller_offers(result.events)[0] >= scenario.product.list_price * 0.95


# --- quality skeptic -------------------------------------------------------


def test_quality_skeptic_inspects_and_discounts_the_lemon():
    scenario = _scenario(seller_true_quality=0.4)  # claim 0.9, truth 0.4
    tools, configs = _inspect_tool(scenario)
    skeptic = ProfileBackedBuyer(profile=_profile("buyer_quality_skeptic_v1"))
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=skeptic,
        seller=ScriptedSeller(name="seller"),
        tools=tools,
        tool_configs=configs,
    )
    result = env.run()
    # It actually used the inspect tool.
    assert any(
        e.role == Role.BUYER
        and e.action_type == ActionType.TOOL_CALL
        and e.tool_call
        and e.tool_call.name == "inspect"
        for e in result.events
    )
    skeptic_offer = _buyer_offers(result.events)[0]

    # A non-skeptic buyer on the same lemon (no inspect) offers more.
    probe = ProfileBackedBuyer(profile=_profile("buyer_budget_probe_v1"))
    probe_env = NegotiationEnvironment(
        scenario=scenario, buyer=probe, seller=ScriptedSeller(name="seller")
    )
    probe_offer = _buyer_offers(probe_env.run().events)[0]
    assert skeptic_offer < probe_offer


class _SilentBuyer:
    name = "silent_buyer"
    role = Role.BUYER

    def act(self, context):
        from opennego.schema import AgentAction

        return AgentAction.message("waiting")


def _silent_buyer():
    return _SilentBuyer()
