"""Co-evolution genome + evolved agents + variation (#229)."""

import random

import pytest

from opennego.agents import ScriptedSeller
from opennego.agents.profiles import BuyerPolicy, SellerPolicy
from opennego.coevolution import (
    GENE_BOUNDS,
    CoevolutionError,
    Genome,
    build_agent,
    crossover,
    mutate,
    random_genome,
    to_policy,
)
from opennego.environment import NegotiationEnvironment
from opennego.schema import ActionType, Product, Role, Scenario


def _scenario():
    product = Product(
        id="g1",
        name="Widget",
        description="d",
        list_price=600.0,
        wholesale_price=300.0,
        condition="used",
    )
    return Scenario(
        product=product, buyer_budget=600.0, seller_reservation_price=300.0, max_turns=6
    )


def test_genome_rejects_wrong_genes():
    with pytest.raises(CoevolutionError):
        Genome(genome_id="x", role=Role.BUYER, genes={"opening_markup": 0.9})


def test_genome_clamps_to_bounds():
    g = Genome(
        genome_id="x",
        role=Role.SELLER,
        genes={
            "opening_markup": 5.0,  # over high
            "concession_fraction": -1.0,  # under low
            "floor_reference_multiplier": 1.0,
        },
    )
    assert g.genes["opening_markup"] == 1.0
    assert g.genes["concession_fraction"] == 0.20


def test_to_policy_maps_to_role_policy():
    buyer_g = random_genome(Role.BUYER, random.Random(1), genome_id="b")
    seller_g = random_genome(Role.SELLER, random.Random(1), genome_id="s")
    assert isinstance(to_policy(buyer_g), BuyerPolicy)
    assert isinstance(to_policy(seller_g), SellerPolicy)


def test_build_agent_drives_a_real_negotiation():
    seller_g = random_genome(Role.SELLER, random.Random(7), genome_id="s1")
    seller = build_agent(seller_g)
    assert seller.role == Role.SELLER
    from opennego.agents import ToolAwareBuyer

    result = NegotiationEnvironment(
        scenario=_scenario(), buyer=ToolAwareBuyer(), seller=seller
    ).run()
    # The evolved policy drove a real, terminating negotiation in which the
    # seller participated.
    assert result.outcome in {"deal", "timeout", "rejected", "ghosted"}
    assert any(e.role == Role.SELLER for e in result.events)


def test_buyer_genome_agent_uses_its_policy():
    # A very low opening_discount buyer opens lower than a high one.
    def first_buyer_offer(discount):
        genes = {
            "opening_discount": discount,
            "counter_fraction": 0.85,
            "willingness_multiplier": 0.95,
            "quality_skepticism": 0.0,
        }
        buyer = build_agent(Genome(genome_id="b", role=Role.BUYER, genes=genes))
        result = NegotiationEnvironment(
            scenario=_scenario(), buyer=buyer, seller=ScriptedSeller()
        ).run()
        offers = [
            e.offer.price
            for e in result.events
            if e.role == Role.BUYER and e.action_type == ActionType.OFFER and e.offer
        ]
        return offers[0]

    assert first_buyer_offer(0.55) < first_buyer_offer(0.95)


def test_mutate_is_deterministic_and_bounded():
    base = random_genome(Role.BUYER, random.Random(3), genome_id="b0")
    a = mutate(base, random.Random(99), genome_id="b1")
    b = mutate(base, random.Random(99), genome_id="b1")
    assert a == b
    assert a.parent_ids == ("b0",)
    for name, (low, high) in GENE_BOUNDS[Role.BUYER].items():
        assert low <= a.genes[name] <= high


def test_crossover_picks_per_gene_from_parents():
    a = Genome(
        genome_id="a",
        role=Role.SELLER,
        genes={"opening_markup": 0.85, "concession_fraction": 0.20, "floor_reference_multiplier": 0.90},
    )
    b = Genome(
        genome_id="b",
        role=Role.SELLER,
        genes={"opening_markup": 1.00, "concession_fraction": 0.70, "floor_reference_multiplier": 1.10},
    )
    child = crossover(a, b, random.Random(5), genome_id="c")
    assert child.parent_ids == ("a", "b")
    for name in GENE_BOUNDS[Role.SELLER]:
        assert child.genes[name] in (a.genes[name], b.genes[name])


def test_crossover_rejects_mixed_roles():
    a = random_genome(Role.BUYER, random.Random(1), genome_id="a")
    b = random_genome(Role.SELLER, random.Random(1), genome_id="b")
    with pytest.raises(CoevolutionError):
        crossover(a, b, random.Random(1), genome_id="c")
