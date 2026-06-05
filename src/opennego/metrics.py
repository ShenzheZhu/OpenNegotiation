"""Evaluation metrics for OpenNego runs."""

from __future__ import annotations

from collections.abc import Sequence

from .schema import ActionType, Scenario, TranscriptEvent


def compute_metrics(
    scenario: Scenario,
    outcome: str,
    deal_price: float | None,
    events: Sequence[TranscriptEvent],
) -> dict[str, float]:
    tool_events = [event for event in events if event.action_type == ActionType.TOOL_CALL]
    tool_call_count = len(tool_events)
    tool_failure_count = sum(
        1
        for event in tool_events
        if event.tool_result and event.tool_result.get("ok") is False
    )
    tool_success_count = tool_call_count - tool_failure_count
    public_tool_call_count = sum(1 for event in tool_events if not event.private)
    private_tool_call_count = tool_call_count - public_tool_call_count
    tool_evidence_event_count = sum(
        1
        for event in tool_events
        if event.tool_result and bool(event.tool_result.get("results"))
    )
    metrics = {
        "deal_rate": 1.0 if outcome == "deal" else 0.0,
        "tool_call_count": float(tool_call_count),
        "tool_success_count": float(tool_success_count),
        "tool_failure_count": float(tool_failure_count),
        "private_tool_call_count": float(private_tool_call_count),
        "public_tool_call_count": float(public_tool_call_count),
        "tool_evidence_event_count": float(tool_evidence_event_count),
    }

    if deal_price is None:
        metrics.update(
            {
                "buyer_savings_vs_list": 0.0,
                "buyer_budget_slack": 0.0,
                "seller_profit_vs_reservation": 0.0,
                "normalized_deal_price": 0.0,
            }
        )
        return metrics

    product = scenario.product
    spread = max(product.list_price - product.wholesale_price, 1.0)
    metrics.update(
        {
            "buyer_savings_vs_list": product.list_price - deal_price,
            "buyer_budget_slack": scenario.buyer_budget - deal_price,
            "seller_profit_vs_reservation": deal_price - scenario.seller_reservation_price,
            "normalized_deal_price": (deal_price - product.wholesale_price) / spread,
        }
    )
    return metrics
