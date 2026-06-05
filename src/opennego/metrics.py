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
    tool_call_count = sum(1 for event in events if event.action_type == ActionType.TOOL_CALL)
    metrics = {
        "deal_rate": 1.0 if outcome == "deal" else 0.0,
        "tool_call_count": float(tool_call_count),
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
