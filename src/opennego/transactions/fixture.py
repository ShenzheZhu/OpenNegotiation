"""Deterministic fixture-backed transaction simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from opennego.ports import TransactionPort, TransactionRequest
from opennego.schema import TransactionOutcome


@dataclass(frozen=True)
class FixtureTransactionSimulator(TransactionPort):
    shipping_cost: float = 0.0
    tax_rate: float = 0.0
    escrow_fee: float = 0.0
    payment_fee_rate: float = 0.0
    seller_fee_rate: float = 0.0
    return_risk: float = 0.0
    reputation_risk: float = 0.0
    payment_success: bool = True
    max_buyer_total_cost: float | None = None
    min_seller_net_revenue: float | None = None
    failure_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def settle(self, request: TransactionRequest) -> TransactionOutcome:
        negotiated_price = request.negotiated_price
        tax = round(negotiated_price * self.tax_rate, 2)
        payment_fee = round(negotiated_price * self.payment_fee_rate, 2)
        seller_fee = round(negotiated_price * self.seller_fee_rate, 2)
        buyer_total_cost = round(
            negotiated_price + self.shipping_cost + tax + self.escrow_fee + payment_fee,
            2,
        )
        seller_net_revenue = round(
            negotiated_price - seller_fee - self.escrow_fee,
            2,
        )
        risk_exposure = round(self.return_risk + self.reputation_risk, 4)
        validation_metadata = self._validation_metadata(
            buyer_total_cost=buyer_total_cost,
            seller_net_revenue=seller_net_revenue,
        )
        if (
            self.max_buyer_total_cost is not None
            and buyer_total_cost > self.max_buyer_total_cost
        ):
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="buyer_total_cost_exceeded",
                metadata={
                    **validation_metadata,
                    "violated_guard": "max_buyer_total_cost",
                },
            )
        if (
            self.min_seller_net_revenue is not None
            and seller_net_revenue < self.min_seller_net_revenue
        ):
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="seller_net_revenue_below_floor",
                metadata={
                    **validation_metadata,
                    "violated_guard": "min_seller_net_revenue",
                },
            )
        if not self.payment_success:
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason=self.failure_reason or "payment_failed",
                metadata=validation_metadata,
            )
        return TransactionOutcome(
            status="completed",
            negotiated_price=negotiated_price,
            buyer_total_cost=buyer_total_cost,
            seller_net_revenue=seller_net_revenue,
            shipping_cost=self.shipping_cost,
            tax=tax,
            escrow_fee=self.escrow_fee,
            payment_fee=payment_fee,
            seller_fee=seller_fee,
            return_risk=self.return_risk,
            reputation_risk=self.reputation_risk,
            risk_exposure=risk_exposure,
            metadata=dict(self.metadata),
        )

    def _validation_metadata(
        self,
        *,
        buyer_total_cost: float,
        seller_net_revenue: float,
    ) -> Mapping[str, Any]:
        metadata = {
            **dict(self.metadata),
            "computed_buyer_total_cost": buyer_total_cost,
            "computed_seller_net_revenue": seller_net_revenue,
        }
        if self.max_buyer_total_cost is not None:
            metadata["max_buyer_total_cost"] = self.max_buyer_total_cost
        if self.min_seller_net_revenue is not None:
            metadata["min_seller_net_revenue"] = self.min_seller_net_revenue
        return metadata

    def _failed_outcome(
        self,
        *,
        negotiated_price: float,
        shipping_cost: float,
        tax: float,
        escrow_fee: float,
        payment_fee: float,
        seller_fee: float,
        risk_exposure: float,
        failure_reason: str,
        metadata: Mapping[str, Any],
    ) -> TransactionOutcome:
        return TransactionOutcome(
            status="failed",
            negotiated_price=negotiated_price,
            buyer_total_cost=0.0,
            seller_net_revenue=0.0,
            shipping_cost=shipping_cost,
            tax=tax,
            escrow_fee=escrow_fee,
            payment_fee=payment_fee,
            seller_fee=seller_fee,
            return_risk=self.return_risk,
            reputation_risk=self.reputation_risk,
            risk_exposure=risk_exposure,
            failure_reason=failure_reason,
            metadata=metadata,
        )
