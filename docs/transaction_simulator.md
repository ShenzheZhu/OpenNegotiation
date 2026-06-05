# Transaction Simulator

OpenNego separates negotiated price from transaction outcome. A deal can be
accepted at a product price and then settled through a deterministic simulator
that adds costs, fees, and risk placeholders.

The first simulator is fixture-backed and intentionally local. It does not call
real payment, escrow, shipping, tax, or marketplace APIs.

## Fixture Factors

`FixtureTransactionSimulator` supports:

- `shipping_cost`: fixed buyer-side shipping cost.
- `tax_rate`: tax rate applied to negotiated price.
- `escrow_fee`: fixed fee included in buyer total cost and deducted from seller
  net revenue.
- `payment_fee_rate`: buyer-side payment processing fee.
- `seller_fee_rate`: seller-side marketplace or platform fee.
- `return_risk`: deterministic return-risk placeholder.
- `reputation_risk`: deterministic counterparty/reputation-risk placeholder.
- `payment_success`: when false, the transaction is recorded as failed.
- `max_buyer_total_cost`: optional all-in buyer cost cap. Settlement fails if
  computed buyer total cost exceeds this value.
- `min_seller_net_revenue`: optional seller net revenue floor. Settlement fails
  if computed seller net revenue is below this value.

For a completed transaction:

```text
buyer_total_cost = negotiated_price + shipping_cost + tax + escrow_fee + payment_fee
seller_net_revenue = negotiated_price - seller_fee - escrow_fee
risk_exposure = return_risk + reputation_risk
```

For a failed transaction, buyer cost and seller revenue are recorded as `0.0`,
while the failed transaction still preserves the computed costs, fees, risks,
and `failure_reason` for audit.

Settlement guard failures use deterministic reasons:

- `buyer_total_cost_exceeded`
- `seller_net_revenue_below_floor`

The failed transaction metadata records:

- `computed_buyer_total_cost`
- `computed_seller_net_revenue`
- the configured guard values
- `violated_guard`

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

## Boundaries

This simulator is suitable for deterministic benchmark comparisons. It is not a
claim about real payment success, legal compliance, tax calculation, logistics,
or platform policy.
