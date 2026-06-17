"""Prompt mutator port + mutators + agent factories (#246)."""

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.environment import NegotiationEnvironment
from opennego.ports import LLMRequest, LLMResponse
from opennego.prompt_evolution import (
    DEFAULT_AGGRESSIVENESS,
    FakePromptMutator,
    LLMPromptMutator,
    PromptGenome,
    fake_agent_factory,
    make_llm_agent_factory,
    parse_aggressiveness,
)
from opennego.schema import ActionType, Product, Role, Scenario


class _RecordingLLM:
    def __init__(self, content):
        self.content = content
        self.requests = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(model=request.model, content=self.content)


def _scenario():
    product = Product(
        id="p1", name="Widget", description="d", list_price=600.0,
        wholesale_price=300.0, condition="used",
    )
    return Scenario(
        product=product, buyer_budget=600.0, seller_reservation_price=300.0, max_turns=6
    )


def test_parse_aggressiveness():
    assert parse_aggressiveness("be tough [[aggr=0.80]]") == 0.80
    assert parse_aggressiveness("no tag") == DEFAULT_AGGRESSIVENESS
    assert parse_aggressiveness("[[aggr=2.0]]") == 1.0  # clamped


def test_fake_mutator_is_deterministic_and_tagged():
    m = FakePromptMutator()
    a = m.mutate("anchor low [[aggr=0.50]]", feedback="lost in closing")
    b = m.mutate("anchor low [[aggr=0.50]]", feedback="lost in closing")
    assert a == b
    assert 0.0 <= parse_aggressiveness(a) <= 1.0
    # Different feedback -> different (deterministic) step.
    assert m.mutate("anchor low [[aggr=0.50]]", feedback="other") != a


def test_fake_mutator_crossover_is_midpoint():
    m = FakePromptMutator()
    child = m.crossover("x [[aggr=0.20]]", "y [[aggr=0.80]]")
    assert abs(parse_aggressiveness(child) - 0.50) < 1e-6


def test_llm_mutator_uses_the_model():
    llm = _RecordingLLM("improved prompt: open lower, hold firm")
    m = LLMPromptMutator(llm=llm, model="fake/model")
    out = m.mutate("open high", feedback="over-conceded")
    assert out == "improved prompt: open lower, hold firm"
    assert llm.requests and llm.requests[0].model == "fake/model"
    # The current prompt and feedback are passed to the model.
    user_msg = llm.requests[0].messages[-1]["content"]
    assert "open high" in user_msg and "over-conceded" in user_msg


def test_llm_mutator_crossover_uses_the_model():
    llm = _RecordingLLM("combined prompt")
    m = LLMPromptMutator(llm=llm, model="fake/model")
    assert m.crossover("A", "B") == "combined prompt"


def test_fake_agent_factory_builds_a_negotiating_agent():
    genome = PromptGenome(genome_id="g1", prompt="be tough [[aggr=0.9]]")
    buyer = fake_agent_factory(genome, Role.BUYER)
    assert buyer.role == Role.BUYER
    result = NegotiationEnvironment(
        scenario=_scenario(), buyer=buyer, seller=ScriptedSeller()
    ).run()
    assert any(e.role == Role.BUYER for e in result.events)


def test_fake_agent_aggressiveness_changes_behavior():
    # A more aggressive buyer opens lower.
    def first_offer(aggr):
        genome = PromptGenome(genome_id="g", prompt=f"p [[aggr={aggr}]]")
        buyer = fake_agent_factory(genome, Role.BUYER)
        result = NegotiationEnvironment(
            scenario=_scenario(), buyer=buyer, seller=ScriptedSeller()
        ).run()
        return [
            e.offer.price
            for e in result.events
            if e.role == Role.BUYER and e.action_type == ActionType.OFFER and e.offer
        ][0]

    assert first_offer(0.9) < first_offer(0.1)


def test_llm_agent_factory_builds_an_agent():
    llm = _RecordingLLM('{"action": "offer", "price": 420, "note": "ok"}')
    factory = make_llm_agent_factory(llm, "fake/model")
    agent = factory(PromptGenome(genome_id="g", prompt="hold firm"), Role.BUYER)
    assert agent.role == Role.BUYER
