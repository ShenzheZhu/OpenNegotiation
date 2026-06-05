from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.environment import NegotiationEnvironment
from opennego.schema import ActionType, Product, Role, Scenario
from opennego.tools import MarketComparable, MarketPriceTool


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


def test_market_tool_returns_comparable_summary():
    result = make_market_tool().call({"query": "Sony a6400 camera", "condition": "used"}, None)  # type: ignore[arg-type]

    assert result["ok"] is True
    assert result["count"] == 3
    assert result["median_price"] == 800.0


def test_tool_call_is_private_and_run_reaches_deal():
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(make_market_tool(),),
    )

    result = env.run()

    assert result.outcome == "deal"
    assert result.deal_price == 760.0
    assert result.metrics["tool_call_count"] == 1.0
    assert result.events[0].action_type == ActionType.TOOL_CALL
    assert result.events[0].private is True


def test_private_tool_result_is_not_visible_to_seller():
    class InspectingSeller(ScriptedSeller):
        saw_buyer_tool_result = False

        def act(self, context):
            self.saw_buyer_tool_result = any(
                event.role == Role.BUYER and event.action_type == ActionType.TOOL_CALL
                for event in context.transcript
            )
            return super().act(context)

    seller = InspectingSeller()
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=ToolAwareBuyer(),
        seller=seller,
        tools=(make_market_tool(),),
    )

    env.run()

    assert seller.saw_buyer_tool_result is False
