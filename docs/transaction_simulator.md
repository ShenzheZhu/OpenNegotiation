# Transaction Simulator

OpenNegotiation separates negotiated price from transaction outcome. A deal can be
accepted at a product price and then settled through a deterministic simulator
that adds costs, fees, lifecycle terms, policy checks, and risk placeholders.

The first simulator is fixture-backed and intentionally local. It does not call
real payment, escrow, shipping, tax, or marketplace APIs.

## Fixture Factors

`FixtureTransactionSimulator` supports:

- `shipping_cost`: fixed buyer-side shipping cost.
- `tax_rate`: tax rate applied to negotiated price.
- `escrow_fee`: fixed fee included in buyer total cost and deducted from seller
  net revenue.
- `payment_fee_rate` / `payment_fee_fixed`: buyer-side payment processing fee.
- `seller_fee_rate` / `seller_fee_fixed`: seller-side marketplace or platform
  fee; `seller_fee_tiers` supports marginal tiered schedules like real
  final-value fees.
- `return_risk`: deterministic return-risk placeholder.
- `reputation_risk`: deterministic counterparty/reputation-risk placeholder.
- `dispute_risk`: deterministic dispute-risk placeholder; included in total
  risk exposure and exposed as a separate metric.
- `payment_success`: when false, the transaction is recorded as failed.
- `shipping_success`: when false, settlement fails after payment validation.
- `item_matches_listing`: when false, settlement fails as an item-mismatch
  dispute.
- `max_buyer_total_cost`: optional all-in buyer cost cap. Settlement fails if
  computed buyer total cost exceeds this value.
- `min_seller_net_revenue`: optional seller net revenue floor. Settlement fails
  if computed seller net revenue is below this value.
- `max_dispute_risk`: optional deterministic dispute-risk cap.
- `return_window_days`: return-window policy attached to the fixture
  transaction.
- `min_return_window_days`: optional minimum acceptable return-window policy.
- `payment_method`, `payment_processor`, and `escrow_release_policy`: fixture
  payment terms preserved in transaction metadata.
- `shipping_carrier`, `shipping_service`, `tracking_required`,
  `delivery_days`, and `max_delivery_days`: fixture logistics terms. Settlement
  fails with `delivery_sla_exceeded` when `delivery_days` exceeds
  `max_delivery_days`.
- `return_shipping_payer` and `inspection_period_days`: return/inspection terms
  preserved for audit.
- `warranty_days`, `min_warranty_days`, and `warranty_provider`: warranty terms.
  Settlement fails with `warranty_below_minimum` when the warranty window is too
  short.
- `compliance_checks` and `compliance_passed`: deterministic compliance terms.
  Settlement fails with `compliance_check_failed` when checks do not pass.
- `dispute_window_days` and `dispute_resolution_policy`: platform-style dispute
  terms preserved in transaction metadata.

For a completed transaction:

```text
buyer_total_cost = negotiated_price + shipping_cost + tax + escrow_fee + payment_fee
seller_net_revenue = negotiated_price - seller_fee - escrow_fee
risk_exposure = return_risk + reputation_risk + dispute_risk
```

For a failed transaction, buyer cost and seller revenue are recorded as `0.0`,
while the failed transaction still preserves the computed costs, fees, risks,
and `failure_reason` for audit.

Settlement guard failures use deterministic reasons:

- `buyer_total_cost_exceeded`
- `seller_net_revenue_below_floor`
- `shipping_failed`
- `item_mismatch_dispute`
- `return_window_below_minimum`
- `delivery_sla_exceeded`
- `warranty_below_minimum`
- `compliance_check_failed`
- `dispute_risk_exceeded`

The failed transaction metadata records:

- `computed_buyer_total_cost`
- `computed_seller_net_revenue`
- `computed_risk_exposure`
- the configured guard values
- lifecycle inputs such as `shipping_success`, `item_matches_listing`,
  `return_window_days`, and `dispute_risk`
- structured `transaction_terms` grouped under payment, logistics, returns,
  warranty, compliance, and dispute sections
- `violated_guard`
- `lifecycle_stage`

The `transaction_terms` metadata object uses schema
`opennego.transaction_terms.v1` and is intentionally provider-neutral. It is a
fixture contract for benchmark and training comparability, not a live payment or
logistics adapter.

## Published Fee Schedules

Instead of inventing fee constants, experiment configs can reference a
published platform schedule by id:

```json
{
  "transaction": {
    "kind": "fixture",
    "enabled": true,
    "schedule": "ebay_us_2026_general"
  }
}
```

Curated schedules live in `opennego/transactions/data/fee_schedules.json`
(`opennego.fee_schedule.v1`). Every entry must carry `source_url` and `as_of`
provenance; entries without provenance fail to load. Shipped schedules:

- `ebay_us_2026_general`: tiered final value fee (13.35% to $7,500, 2.35%
  above) plus a fixed per-order amount, payment processing included,
  representative blended marketplace-facilitator tax rate.
- `paypal_gs_us_2026`: direct peer-to-peer sale via PayPal Goods and
  Services; the receiving seller pays 2.99% plus a fixed fee.
- `local_cash_pickup`: zero-fee local meetup with no buyer protection.

Explicit keys in the `transaction` block override schedule values. Run
manifests record the schedule id, `as_of` date, and resolved fee parameters
under `metadata.transaction`.

## Trace Contract

When a deal is accepted and a transaction simulator is attached,
`NegotiationEnvironment` appends a public system event:

```json
{
  "role": "system",
  "actor": "transaction_simulator",
  "action_type": "transaction",
  "content": "completed",
  "transaction": {
    "status": "completed",
    "negotiated_price": 760.0,
    "buyer_total_cost": 858.0,
    "seller_net_revenue": 718.0
  }
}
```

The metrics report keeps negotiation and transaction quantities separate:

- `deal_rate`
- `normalized_deal_price`
- `buyer_total_transaction_cost`
- `seller_net_transaction_revenue`
- `transaction_completed_rate`
- `failed_transaction_rate`
- `transaction_risk_exposure`
- `transaction_dispute_risk`

## Boundaries

This simulator is suitable for deterministic benchmark comparisons. It is not a
claim about real payment success, legal compliance, tax calculation, logistics,
returns, disputes, warranties, or platform policy. Live providers should be
implemented behind future transaction adapters rather than inside the fixture
simulator or core environment.
