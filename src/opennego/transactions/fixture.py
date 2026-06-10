"""Deterministic fixture-backed transaction simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from opennego.ports import TransactionPort, TransactionRequest
from opennego.schema import TransactionOutcome
from opennego.transactions.fee_schedules import tiered_seller_fee


@dataclass(frozen=True)
class FixtureTransactionSimulator(TransactionPort):
    shipping_cost: float = 0.0
    tax_rate: float = 0.0
    escrow_fee: float = 0.0
    payment_fee_rate: float = 0.0
    payment_fee_fixed: float = 0.0
    seller_fee_rate: float = 0.0
    seller_fee_fixed: float = 0.0
    seller_fee_tiers: tuple[tuple[float | None, float], ...] = ()
    return_risk: float = 0.0
    reputation_risk: float = 0.0
    dispute_risk: float = 0.0
    payment_success: bool = True
    shipping_success: bool = True
    item_matches_listing: bool = True
    max_buyer_total_cost: float | None = None
    min_seller_net_revenue: float | None = None
    max_dispute_risk: float | None = None
    return_window_days: int | None = None
    min_return_window_days: int | None = None
    payment_method: str | None = None
    payment_processor: str | None = None
    escrow_release_policy: str | None = None
    shipping_carrier: str | None = None
    shipping_service: str | None = None
    tracking_required: bool = False
    delivery_days: int | None = None
    max_delivery_days: int | None = None
    return_shipping_payer: str | None = None
    inspection_period_days: int | None = None
    warranty_days: int | None = None
    min_warranty_days: int | None = None
    warranty_provider: str | None = None
    compliance_checks: tuple[str, ...] = ()
    compliance_passed: bool = True
    dispute_window_days: int | None = None
    dispute_resolution_policy: str | None = None
    failure_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def settle(self, request: TransactionRequest) -> TransactionOutcome:
        negotiated_price = request.negotiated_price
        tax = round(negotiated_price * self.tax_rate, 2)
        payment_fee = round(
            negotiated_price * self.payment_fee_rate + self.payment_fee_fixed, 2
        )
        seller_fee = tiered_seller_fee(
            negotiated_price,
            self.seller_fee_tiers,
            fallback_rate=self.seller_fee_rate,
            fixed=self.seller_fee_fixed,
        )
        buyer_total_cost = round(
            negotiated_price + self.shipping_cost + tax + self.escrow_fee + payment_fee,
            2,
        )
        seller_net_revenue = round(
            negotiated_price - seller_fee - self.escrow_fee,
            2,
        )
        risk_exposure = round(
            self.return_risk + self.reputation_risk + self.dispute_risk,
            4,
        )
        validation_metadata = self._validation_metadata(
            buyer_total_cost=buyer_total_cost,
            seller_net_revenue=seller_net_revenue,
            risk_exposure=risk_exposure,
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
                metadata={
                    **validation_metadata,
                    "violated_guard": "payment_success",
                    "lifecycle_stage": "payment",
                },
            )
        if not self.shipping_success:
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="shipping_failed",
                metadata={
                    **validation_metadata,
                    "violated_guard": "shipping_success",
                    "lifecycle_stage": "shipping",
                },
            )
        if (
            self.max_delivery_days is not None
            and self.delivery_days is not None
            and self.delivery_days > self.max_delivery_days
        ):
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="delivery_sla_exceeded",
                metadata={
                    **validation_metadata,
                    "violated_guard": "max_delivery_days",
                    "lifecycle_stage": "logistics",
                },
            )
        if not self.item_matches_listing:
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="item_mismatch_dispute",
                metadata={
                    **validation_metadata,
                    "violated_guard": "item_matches_listing",
                    "lifecycle_stage": "dispute",
                },
            )
        if (
            self.min_return_window_days is not None
            and (self.return_window_days or 0) < self.min_return_window_days
        ):
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="return_window_below_minimum",
                metadata={
                    **validation_metadata,
                    "violated_guard": "min_return_window_days",
                    "lifecycle_stage": "returns",
                },
            )
        if (
            self.min_warranty_days is not None
            and (self.warranty_days or 0) < self.min_warranty_days
        ):
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="warranty_below_minimum",
                metadata={
                    **validation_metadata,
                    "violated_guard": "min_warranty_days",
                    "lifecycle_stage": "warranty",
                },
            )
        if not self.compliance_passed:
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="compliance_check_failed",
                metadata={
                    **validation_metadata,
                    "violated_guard": "compliance_passed",
                    "lifecycle_stage": "compliance",
                },
            )
        if (
            self.max_dispute_risk is not None
            and self.dispute_risk > self.max_dispute_risk
        ):
            return self._failed_outcome(
                negotiated_price=negotiated_price,
                shipping_cost=self.shipping_cost,
                tax=tax,
                escrow_fee=self.escrow_fee,
                payment_fee=payment_fee,
                seller_fee=seller_fee,
                risk_exposure=risk_exposure,
                failure_reason="dispute_risk_exceeded",
                metadata={
                    **validation_metadata,
                    "violated_guard": "max_dispute_risk",
                    "lifecycle_stage": "dispute",
                },
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
            dispute_risk=self.dispute_risk,
            risk_exposure=risk_exposure,
            metadata={
                **validation_metadata,
                "lifecycle_stage": "completed",
            },
        )

    def _validation_metadata(
        self,
        *,
        buyer_total_cost: float,
        seller_net_revenue: float,
        risk_exposure: float,
    ) -> Mapping[str, Any]:
        metadata = {
            **dict(self.metadata),
            "computed_buyer_total_cost": buyer_total_cost,
            "computed_seller_net_revenue": seller_net_revenue,
            "computed_risk_exposure": risk_exposure,
            "dispute_risk": self.dispute_risk,
            "shipping_success": self.shipping_success,
            "item_matches_listing": self.item_matches_listing,
            "transaction_terms": self._transaction_terms(),
        }
        if self.max_buyer_total_cost is not None:
            metadata["max_buyer_total_cost"] = self.max_buyer_total_cost
        if self.min_seller_net_revenue is not None:
            metadata["min_seller_net_revenue"] = self.min_seller_net_revenue
        if self.max_dispute_risk is not None:
            metadata["max_dispute_risk"] = self.max_dispute_risk
        if self.return_window_days is not None:
            metadata["return_window_days"] = self.return_window_days
        if self.min_return_window_days is not None:
            metadata["min_return_window_days"] = self.min_return_window_days
        if self.delivery_days is not None:
            metadata["delivery_days"] = self.delivery_days
        if self.max_delivery_days is not None:
            metadata["max_delivery_days"] = self.max_delivery_days
        if self.warranty_days is not None:
            metadata["warranty_days"] = self.warranty_days
        if self.min_warranty_days is not None:
            metadata["min_warranty_days"] = self.min_warranty_days
        metadata["compliance_passed"] = self.compliance_passed
        return metadata

    def _transaction_terms(self) -> Mapping[str, Any]:
        return {
            "schema_version": "opennego.transaction_terms.v1",
            "payment": _compact(
                {
                    "method": self.payment_method,
                    "processor": self.payment_processor,
                    "escrow_fee": self.escrow_fee,
                    "escrow_release_policy": self.escrow_release_policy,
                    "success": self.payment_success,
                }
            ),
            "logistics": _compact(
                {
                    "shipping_cost": self.shipping_cost,
                    "carrier": self.shipping_carrier,
                    "service": self.shipping_service,
                    "tracking_required": self.tracking_required,
                    "shipping_success": self.shipping_success,
                    "delivery_days": self.delivery_days,
                    "max_delivery_days": self.max_delivery_days,
                }
            ),
            "returns": _compact(
                {
                    "return_window_days": self.return_window_days,
                    "min_return_window_days": self.min_return_window_days,
                    "return_shipping_payer": self.return_shipping_payer,
                    "inspection_period_days": self.inspection_period_days,
                }
            ),
            "warranty": _compact(
                {
                    "warranty_days": self.warranty_days,
                    "min_warranty_days": self.min_warranty_days,
                    "provider": self.warranty_provider,
                }
            ),
            "compliance": _compact(
                {
                    "checks": list(self.compliance_checks),
                    "passed": self.compliance_passed,
                }
            ),
            "dispute": _compact(
                {
                    "risk": self.dispute_risk,
                    "max_dispute_risk": self.max_dispute_risk,
                    "window_days": self.dispute_window_days,
                    "resolution_policy": self.dispute_resolution_policy,
                    "item_matches_listing": self.item_matches_listing,
                }
            ),
        }

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
            dispute_risk=self.dispute_risk,
            risk_exposure=risk_exposure,
            failure_reason=failure_reason,
            metadata=metadata,
        )


def _compact(data: Mapping[str, Any]) -> Mapping[str, Any]:
    return {key: value for key, value in data.items() if value is not None}
