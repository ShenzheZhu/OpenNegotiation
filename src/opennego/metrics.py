"""Evaluation metrics for OpenNego runs."""

from __future__ import annotations

from collections.abc import Sequence

from .schema import ActionType, Scenario, TransactionOutcome, TranscriptEvent


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
    transaction = _latest_transaction(events)
    metrics.update(_transaction_metrics(transaction))

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


def _latest_transaction(events: Sequence[TranscriptEvent]) -> TransactionOutcome | None:
    for event in reversed(events):
        if event.action_type == ActionType.TRANSACTION and event.transaction is not None:
            return event.transaction
    return None


def _transaction_metrics(transaction: TransactionOutcome | None) -> dict[str, float]:
    if transaction is None:
        return {
            "transaction_completed_rate": 0.0,
            "failed_transaction_rate": 0.0,
            "buyer_total_transaction_cost": 0.0,
            "seller_net_transaction_revenue": 0.0,
            "transaction_risk_exposure": 0.0,
            "transaction_shipping_cost": 0.0,
            "transaction_tax": 0.0,
            "transaction_fees": 0.0,
        }
    completed = transaction.status == "completed"
    return {
        "transaction_completed_rate": 1.0 if completed else 0.0,
        "failed_transaction_rate": 0.0 if completed else 1.0,
        "buyer_total_transaction_cost": transaction.buyer_total_cost,
        "seller_net_transaction_revenue": transaction.seller_net_revenue,
        "transaction_risk_exposure": transaction.risk_exposure,
        "transaction_shipping_cost": transaction.shipping_cost,
        "transaction_tax": transaction.tax,
        "transaction_fees": (
            transaction.escrow_fee + transaction.payment_fee + transaction.seller_fee
        ),
    }
