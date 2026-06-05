# Real-Market Benchmark Design

This note defines the first market-grounded OpenNego slice. It is intentionally
small enough for local demos and advisor discussions. It is not a live eBay
collector and it is not a large model sweep.

## Motivation

A realistic buyer agent should not negotiate from static prompts alone. It can
search comparable sales, compare conditions, reason about fees and shipping,
and then bargain. A realistic seller agent may also use market evidence, demand
signals, reputation, or transaction risk.

OpenNego should therefore evaluate negotiation as one phase in an agentic market
workflow:

1. Build a product cluster.
2. Attach market evidence and provenance.
3. Expose tools under controlled information regimes.
4. Run structured buyer-seller negotiation.
5. Settle accepted deals through transaction simulators.
6. Score against market references, constraints, tool behavior, and settlement
   validity.

## Data Unit

The real-market dataset unit should be a product cluster, not a single listing.
For example:

```text
Apple iPhone 14 Pro 128GB Unlocked, used good condition
```

A cluster should store normalized product attributes and recent sold comparable
statistics:

- product title, category, condition, and salient attributes
- current or synthetic asking price used as the seller anchor
- sold-price reference, such as median or another declared estimator
- p25/p75 or another robust spread for normalized market-gap scoring
- sample size, marketplace, collection window, and currency
- sale mechanism when available, such as auction, buy-it-now, best offer, or
  mixed
- provenance and collection timestamp

The current fixture format stores this in `product.market_reference`.

## Cost Price Policy

Human-observed seller cost is not generally available in C2C markets. OpenNego
should not treat cost price as a public benchmark truth.

For compatibility with the initial environment, the current schema still keeps a
legacy `wholesale_price` field. In market-style records this field may be
derived from a synthetic seller reservation price or from the lower side of the
market reference distribution. The artifact records
`legacy_wholesale_basis` when this happens.

The intended benchmark semantics are:

- market reference is the observed external anchor
- buyer budget is a role-specific private constraint
- seller reservation is a simulator-private constraint
- seller cost is not a human-ground-truth label
- leaderboard metrics should not claim to recover true seller profit

## Leaderboard Tracks

The first public leaderboard should use a scorecard, not pure Elo.

Primary tracks:

- Buyer Track: candidate buyer agent vs standardized seller.
- Seller Track: candidate seller agent vs standardized buyer.
- Tool-Aware Track: same role tracks with controlled market-search tools.
- Transaction Track: accepted deals must pass settlement simulation.

Secondary track:

- Mini Arena: smaller model-vs-model or self-play subset, with Elo or
  Bradley-Terry as an exploratory ranking.

This keeps the broad benchmark stable and interpretable while still allowing
arena-style comparison where pairwise cost is acceptable.

## Metrics

The current prototype adds market-reference metrics:

- `market_reference_price`
- `market_price_gap`
- `normalized_market_gap`
- `buyer_savings_vs_market_reference`
- `seller_revenue_vs_market_reference`

These sit next to existing metrics for deal rate, budget slack, reservation
slack, tool use, transaction completion, fees, and risk.

For leaderboard aggregation, use macro averages by category so high-volume
electronics do not dominate all scores.

## Human Market Gap

Sold prices are human market outcomes, but not always human negotiations.
Auction, buy-it-now, and best-offer sales are different mechanisms. OpenNego
should use careful naming:

- `human market outcome gap` for broad sold-price comparison
- `human negotiation gap` only for subsets where explicit negotiated-sale
  evidence is available

## Data Source Boundary

The framework should use a `MarketDataPort` and frozen benchmark artifacts. It
should not assume that live marketplace data is always available during eval.

Official or licensed data sources can be adapted later. The no-key demo uses
fixture-backed sold comps only. Live collection, marketplace API credentials,
and scraping are out of scope for the initial benchmark slice.

## Offline Sold-Comps Ingestion

Local CSV or JSON-list exports can be normalized into OpenNego fixtures without
live marketplace access:

```bash
opennego ingest-market \
  --input /tmp/sold_comps.csv \
  --products-output /tmp/opennego-products.json \
  --comps-output /tmp/opennego-market-comps.json \
  --manifest-output /tmp/opennego-market-dataset.json \
  --source ebay_offline_export \
  --window-days 90
```

The ingester accepts common field names for product/query, listing title,
sold/final price, condition, marketplace/source, sale mechanism, currency, and
sold date. It writes:

- `products.json`: product clusters with `market_reference` median, p25, p75,
  sample size, currency, source, sale mechanism, and ingestion metadata.
- `market_comps.json`: comparable records loadable by `MarketPriceTool`.
- `market_dataset.json`: optional aggregate manifest with schema version,
  source file SHA-256, output paths, product/comparable counts, price summary,
  missing-date counts, grouped source/condition/mechanism stats, and cluster
  summaries.

This is an offline normalization path only. It does not scrape websites, call
marketplace APIs, bypass marketplace terms, or store live credentials. The
dataset manifest intentionally stores aggregate quality statistics and does not
copy raw listing titles.

## Demo Commands

Run a tiny fixture-backed market demo:

```bash
opennego run --config configs/real_market_demo.yaml --output-dir /tmp/opennego-real-market-demo
```

Generate the static HTML dashboard:

```bash
opennego report --input-dir /tmp/opennego-real-market-demo --output /tmp/opennego-real-market-demo.html
```

Open the report in a browser for a visual discussion surface.
