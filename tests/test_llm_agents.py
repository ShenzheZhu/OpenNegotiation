import inspect
import json

import pytest

import opennego.agents.llm as llm_agents
from opennego.agents import ScriptedSeller, make_llm_buyer, make_profile_llm_agent
from opennego.environment import NegotiationEnvironment
from opennego.learning import load_strategy_registry
from opennego.ports import LLMRequest, LLMResponse
from opennego.schema import ActionType, AgentContext, Product, Role, Scenario
from opennego.tools import MarketComparable, MarketPriceTool


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("FakeLLM received more requests than expected")
        return LLMResponse(model=request.model, content=self.responses.pop(0))


def make_scenario() -> Scenario:
    product = Product(
        id="camera_001",
        name="Sony Alpha a6400 Mirrorless Camera Body",
        description="Used mirrorless camera body.",
        condition="used",
        list_price=1000.0,
        wholesale_price=620.0,
    )
    return Scenario(
        product=product,
        buyer_budget=850.0,
        seller_reservation_price=620.0,
        max_turns=6,
    )


def make_context(*, available_tools=()) -> AgentContext:
    return AgentContext(
        scenario=make_scenario(),
        role=Role.BUYER,
        transcript=(),
        available_tools=tuple(available_tools),
        private_state={"budget": 850.0},
    )


def make_market_tool() -> MarketPriceTool:
    return MarketPriceTool(
        [
            MarketComparable(
                query="Sony Alpha a6400 Mirrorless Camera Body",
                title="Sony a6400 body only",
                price=790.0,
                source="fixture",
                condition="used",
            ),
            MarketComparable(
                query="Sony Alpha a6400 Mirrorless Camera Body",
                title="Sony a6400 with battery",
                price=800.0,
                source="fixture",
                condition="used",
            ),
            MarketComparable(
                query="Sony Alpha a6400 Mirrorless Camera Body",
                title="Sony Alpha a6400 lightly used",
                price=810.0,
                source="fixture",
                condition="used",
            ),
        ]
    )


@pytest.mark.parametrize(
    ("response", "expected_type"),
    [
        (
            '{"type": "offer", "price": 750, "note": "My offer is $750."}',
            ActionType.OFFER,
        ),
        ('{"type": "accept", "note": "Accepted."}', ActionType.ACCEPT),
        ('{"type": "reject", "note": "No deal."}', ActionType.REJECT),
        (
            '{"type": "message", "content": "Can you include shipping?"}',
            ActionType.MESSAGE,
        ),
        (
            '{"type": "tool_call", "tool": {"name": "market_price_search", '
            '"arguments": {"query": "Sony Alpha a6400 Mirrorless Camera Body"}}}',
            ActionType.TOOL_CALL,
        ),
    ],
)
def test_fake_llm_covers_structured_actions(response, expected_type):
    tool_policy = "available" if expected_type == ActionType.TOOL_CALL else "none"
    context = make_context(available_tools=("market_price_search",))
    fake_llm = FakeLLM([response])
    agent = make_llm_buyer(
        llm=fake_llm,
        model="fake/buyer",
        tool_policy=tool_policy,
    )

    action = agent.act(context)

    assert action.type == expected_type
    assert fake_llm.requests[0].response_format is not None
    if expected_type == ActionType.OFFER:
        assert action.offer is not None
        assert action.offer.price == 750.0
    if expected_type == ActionType.TOOL_CALL:
        assert action.tool_call is not None
        assert action.tool_call.name == "market_price_search"


def test_llm_action_response_format_is_strict_provider_schema():
    response_format = llm_agents.LLM_ACTION_RESPONSE_FORMAT

    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    object_schemas = _collect_object_schemas(schema)
    assert object_schemas
    assert all(item.get("additionalProperties") is False for item in object_schemas)

    arguments_schema = schema["properties"]["tool"]["properties"]["arguments"]
    assert arguments_schema["additionalProperties"] is False
    assert set(arguments_schema["properties"]) == {"query", "condition", "limit"}


def test_tool_action_parser_drops_null_structured_output_arguments():
    action = llm_agents.parse_llm_agent_action(
        json.dumps(
            {
                "type": "tool_call",
                "content": None,
                "price": None,
                "note": None,
                "tool": {
                    "name": "market_price_search",
                    "arguments": {
                        "query": "Sony Alpha a6400 Mirrorless Camera Body",
                        "condition": None,
                        "limit": None,
                    },
                },
            }
        ),
        allowed_tools=("market_price_search",),
    )

    assert action.type == ActionType.TOOL_CALL
    assert action.content == ""
    assert action.tool_call is not None
    assert action.tool_call.arguments == {
        "query": "Sony Alpha a6400 Mirrorless Camera Body"
    }


def _collect_object_schemas(schema):
    found = []
    if isinstance(schema, dict):
        schema_type = schema.get("type")
        if schema_type == "object" or (
            isinstance(schema_type, list) and "object" in schema_type
        ):
            found.append(schema)
        for value in schema.values():
            found.extend(_collect_object_schemas(value))
    elif isinstance(schema, list):
        for item in schema:
            found.extend(_collect_object_schemas(item))
    return found


def test_no_tool_llm_agent_repairs_disallowed_tool_call_even_when_tools_exist():
    fake_llm = FakeLLM(
        [
            (
                '{"type": "tool_call", "tool": {"name": "market_price_search", '
                '"arguments": {"query": "camera"}}}'
            ),
            '{"type": "offer", "price": 775, "note": "No-tool offer."}',
        ]
    )
    agent = make_llm_buyer(
        llm=fake_llm,
        model="fake/buyer",
        tool_policy="none",
    )

    action = agent.act(make_context(available_tools=("market_price_search",)))

    assert action.type == ActionType.OFFER
    assert action.tool_call is None
    assert len(fake_llm.requests) == 2
    context_payload = json.loads(fake_llm.requests[0].messages[1]["content"])
    assert context_payload["available_tools"] == []


def test_tool_aware_llm_agent_can_call_market_tool_then_negotiate():
    fake_llm = FakeLLM(
        [
            (
                '{"type": "tool_call", "content": "Checking comps.", '
                '"tool": {"name": "market_price_search", "arguments": '
                '{"query": "Sony Alpha a6400 Mirrorless Camera Body", '
                '"condition": "used", "limit": 3}}}'
            ),
            '{"type": "offer", "price": 760, "note": "Market-backed offer."}',
        ]
    )
    buyer = make_llm_buyer(
        llm=fake_llm,
        model="fake/buyer",
        tool_policy="available",
    )
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=buyer,
        seller=ScriptedSeller(),
        tools=(make_market_tool(),),
    )

    result = env.run()

    assert result.outcome == "deal"
    assert result.deal_price == 760.0
    assert result.events[0].action_type == ActionType.TOOL_CALL
    assert result.events[0].private is True
    assert result.events[0].tool_result["median_price"] == 800.0
    assert len(fake_llm.requests) == 2


def test_profile_llm_agent_injects_strategy_profile_prompt():
    profile = load_strategy_registry().by_id("seller_hardline_anchor_v1")
    fake_llm = FakeLLM(
        ['{"type": "offer", "price": 625, "note": "Profile-backed offer."}']
    )
    agent = make_profile_llm_agent(
        profile=profile,
        llm=fake_llm,
        model="fake/profile-seller",
        max_tokens=128,
    )
    context = AgentContext(
        scenario=make_scenario(),
        role=Role.SELLER,
        transcript=(),
        available_tools=(),
        private_state={"reservation_price": 620.0},
    )

    action = agent.act(context)
    system_prompt = fake_llm.requests[0].messages[0]["content"]

    assert action.type == ActionType.OFFER
    assert agent.role == Role.SELLER
    assert agent.name == "llm_profile_seller:seller_hardline_anchor_v1"
    assert "Additional strategy instructions" in system_prompt
    assert "seller_hardline_anchor_v1" in system_prompt
    assert profile.strategy_prompt in system_prompt
    assert fake_llm.requests[0].metadata["agent_role"] == "seller"


def test_llm_buyer_injects_user_strategy_candidate_prompt():
    fake_llm = FakeLLM(
        ['{"type": "offer", "price": 760, "note": "Strategy-aware offer."}']
    )
    agent = make_llm_buyer(
        llm=fake_llm,
        model="fake/buyer",
        system_instructions=(
            "User strategy candidate id: buyer_baseline-iter-1\n"
            "Strategy prompt:\nAnchor on market comps before conceding."
        ),
    )

    action = agent.act(make_context())
    system_prompt = fake_llm.requests[0].messages[0]["content"]

    assert action.type == ActionType.OFFER
    assert "Additional strategy instructions" in system_prompt
    assert "buyer_baseline-iter-1" in system_prompt
    assert "Anchor on market comps before conceding." in system_prompt
    assert fake_llm.requests[0].metadata["agent_role"] == "buyer"


def test_llm_agent_module_does_not_import_litellm():
    assert "litellm" not in inspect.getsource(llm_agents).lower()
