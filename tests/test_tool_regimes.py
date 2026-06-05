from dataclasses import dataclass, field

import pytest

from opennego.agents import ScriptedSeller
from opennego.artifacts import load_metric_report
from opennego.environment import NegotiationEnvironment, ToolRuntimeConfig
from opennego.runner import run_experiment_config
from opennego.schema import ActionType, AgentAction, AgentContext, Product, Role, Scenario
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


def make_market_tool(*, mode: str = "clean") -> MarketPriceTool:
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
        ],
        mode=mode,
        stale_as_of="2024-01-01",
    )


@dataclass
class SequenceAgent:
    name: str
    role: Role
    actions: list[AgentAction] = field(default_factory=list)

    def act(self, context: AgentContext) -> AgentAction:
        if self.actions:
            return self.actions.pop(0)
        return AgentAction.reject("done")


class InspectingSeller(ScriptedSeller):
    saw_buyer_tool_result = False

    def act(self, context: AgentContext) -> AgentAction:
        self.saw_buyer_tool_result = any(
            event.role == Role.BUYER and event.action_type == ActionType.TOOL_CALL
            for event in context.transcript
        )
        return super().act(context)


class ExplodingTool:
    name = "market_price_search"
    description = "Always raises for fail-fast tests."

    def call(self, arguments, context):
        raise RuntimeError("boom")


def test_tool_visibility_controls_counterparty_transcript():
    for visibility, expected_seen in [("private", False), ("public", True)]:
        buyer = SequenceAgent(
            name=f"buyer_{visibility}",
            role=Role.BUYER,
            actions=[
                AgentAction.tool(
                    "market_price_search",
                    {"query": "Sony Alpha a6400 Mirrorless Camera Body"},
                ),
                AgentAction.offer_price(760, "offer"),
            ],
        )
        seller = InspectingSeller()
        env = NegotiationEnvironment(
            scenario=make_scenario(),
            buyer=buyer,
            seller=seller,
            tools=(make_market_tool(),),
            tool_configs=(
                ToolRuntimeConfig(
                    name="market_price_search",
                    roles=(Role.BUYER,),
                    visibility=visibility,
                ),
            ),
        )

        result = env.run()

        assert result.outcome == "deal"
        assert result.events[0].private is (visibility == "private")
        assert result.events[0].tool_result["visibility"] == visibility
        assert seller.saw_buyer_tool_result is expected_seen


def test_unavailable_role_tool_call_is_structured_failure_not_crash():
    buyer = SequenceAgent(
        name="buyer",
        role=Role.BUYER,
        actions=[AgentAction.message("seller turn")],
    )
    seller = SequenceAgent(
        name="seller",
        role=Role.SELLER,
        actions=[
            AgentAction.tool(
                "market_price_search",
                {"query": "Sony Alpha a6400 Mirrorless Camera Body"},
            ),
            AgentAction.reject("done"),
        ],
    )
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=buyer,
        seller=seller,
        tools=(make_market_tool(),),
        tool_configs=(
            ToolRuntimeConfig(
                name="market_price_search",
                roles=(Role.BUYER,),
                visibility="private",
            ),
        ),
    )

    result = env.run()
    tool_event = result.events[1]

    assert result.outcome == "rejected"
    assert tool_event.tool_result["ok"] is False
    assert "not available" in tool_event.tool_result["error"]
    assert result.metrics["tool_failure_count"] == 1.0


def test_failure_mode_is_recorded_as_tool_failure():
    buyer = SequenceAgent(
        name="buyer",
        role=Role.BUYER,
        actions=[
            AgentAction.tool(
                "market_price_search",
                {"query": "Sony Alpha a6400 Mirrorless Camera Body"},
            ),
            AgentAction.offer_price(800, "fallback offer"),
        ],
    )
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=buyer,
        seller=ScriptedSeller(),
        tools=(make_market_tool(mode="failure"),),
        tool_configs=(
            ToolRuntimeConfig(
                name="market_price_search",
                roles=(Role.BUYER,),
                visibility="private",
            ),
        ),
    )

    result = env.run()

    assert result.outcome == "deal"
    assert result.events[0].tool_result["ok"] is False
    assert result.events[0].tool_result["error"] == "configured market_price_search failure"
    assert result.metrics["tool_failure_count"] == 1.0
    assert result.metrics["tool_success_count"] == 0.0


def test_tool_exception_respects_fail_fast_policy():
    buyer = SequenceAgent(
        name="buyer",
        role=Role.BUYER,
        actions=[
            AgentAction.tool("market_price_search", {"query": "camera"}),
            AgentAction.reject("done"),
        ],
    )
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=buyer,
        seller=ScriptedSeller(),
        tools=(ExplodingTool(),),
        tool_configs=(
            ToolRuntimeConfig(
                name="market_price_search",
                roles=(Role.BUYER,),
                fail_fast=False,
            ),
        ),
    )

    result = env.run()

    assert result.events[0].tool_result["ok"] is False
    assert result.events[0].tool_result["error"] == "boom"

    fail_fast_buyer = SequenceAgent(
        name="buyer",
        role=Role.BUYER,
        actions=[AgentAction.tool("market_price_search", {"query": "camera"})],
    )
    fail_fast_env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=fail_fast_buyer,
        seller=ScriptedSeller(),
        tools=(ExplodingTool(),),
        tool_configs=(
            ToolRuntimeConfig(
                name="market_price_search",
                roles=(Role.BUYER,),
                fail_fast=True,
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="boom"):
        fail_fast_env.run()


def test_market_tool_modes_preserve_provenance():
    stale = make_market_tool(mode="stale").call(
        {"query": "Sony Alpha a6400 Mirrorless Camera Body"},
        None,
    )
    adversarial = MarketPriceTool(
        make_market_tool().comparables,
        mode="adversarial",
        adversarial_multiplier=1.25,
    ).call({"query": "Sony Alpha a6400 Mirrorless Camera Body"}, None)

    assert stale["ok"] is True
    assert stale["mode"] == "stale"
    assert stale["provenance"][0]["stale_as_of"] == "2024-01-01"
    assert adversarial["median_price"] == 1000.0
    assert adversarial["results"][0]["original_price"] != adversarial["results"][0]["price"]


def test_no_key_smoke_config_runs_explicit_tool_regime_matrix(tmp_path):
    summary = run_experiment_config(
        "configs/no_key_smoke.yaml",
        output_dir=tmp_path / "runs",
    )

    assert summary.total_runs == 5
    assert summary.completed == 5
    assert summary.failed == 0

    failure_run = tmp_path / "runs" / (
        "no_key_smoke-camera_001-buyer_private_failure_market_search-seed-7"
    )
    metrics = load_metric_report(failure_run / "metrics.json")
    assert metrics.metrics["tool_failure_count"] == 1.0
