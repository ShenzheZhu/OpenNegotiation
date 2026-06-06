# Real-Market Benchmark Design

This note defines the first market-grounded OpenNegotiation slice. It is intentionally
small enough for local demos and advisor discussions. It is not a live eBay
collector and it is not a large model sweep.

## Motivation

A realistic buyer agent should not negotiate from static prompts alone. It can
search comparable sales, compare conditions, reason about fees and shipping,
and then bargain. A realistic seller agent may also use market evidence, demand
signals, reputation, or transaction risk.

OpenNegotiation should therefore evaluate negotiation as one phase in an agentic market
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

Human-observed seller cost is not generally available in C2C markets. OpenNegotiation
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
Auction, buy-it-now, and best-offer sales are different mechanisms. OpenNegotiation
should use careful naming:

- `human market outcome gap` for broad sold-price comparison
- `human negotiation gap` only for subsets where explicit negotiated-sale
  evidence is available

## Data Source Boundary

The framework should use a `MarketDataPort` and frozen benchmark artifacts. It
should not assume that live marketplace data is always available during eval.

Official or licensed data sources should enter the gym through source adapters
that emit frozen benchmark artifacts. The no-key demo uses fixture-backed sold
comps only. The eBay Marketplace Insights adapter contract supports an official
API path for sold-comps ingestion, but production use still requires eBay
Marketplace Insights access and credentials. eBay's docs mark Marketplace
Insights as Limited Release, so ordinary developer keys may not be enough for
production sold-comps access. Scraping marketplace web pages is out of scope.

Before adding any live or official source adapter, create and validate a source
policy artifact:

```bash
opennego market-source-policy \
  --output /tmp/ebay-source-policy.json \
  --source-id ebay_offline_export \
  --adapter-kind offline_export \
  --collection-mode offline_export \
  --data-rights user_provided_export
opennego validate-market-source \
  --policy /tmp/ebay-source-policy.json
```

The policy uses schema `opennego.market_source_policy.v1` and records source id,
adapter kind, collection mode, data rights, terms URL when relevant, privacy
classification, allowed/prohibited fields, credential policy, retention policy,
and the anti-scraping boundary. Live collection is disabled by default. If a
future adapter enables live collection, validation requires an official API or
licensed dataset mode, a terms/license URL, explicit non-export data rights, and
the `no_credentials_in_repo` and
`no_automated_scraping_without_source_permission` policies.

## Offline Sold-Comps Ingestion

Local CSV or JSON-list exports can be normalized into OpenNegotiation fixtures without
live marketplace access:

```bash
opennego ingest-market \
  --input /tmp/sold_comps.csv \
  --products-output /tmp/opennego-products.json \
  --comps-output /tmp/opennego-market-comps.json \
  --manifest-output /tmp/opennego-market-dataset.json \
  --source-policy /tmp/ebay-source-policy.json \
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
  summaries. When `--source-policy` is supplied, the manifest also records a
  validated source-policy summary and SHA-256.

This is an offline normalization path only. It does not scrape websites, call
marketplace APIs, bypass marketplace terms, or store live credentials. The
dataset manifest intentionally stores aggregate quality statistics and does not
copy raw listing titles.

## eBay Marketplace Insights Adapter

The eBay adapter fetches a bounded sold-comps snapshot from the official
Marketplace Insights API and then feeds the sanitized records into the offline
normalizer above. This keeps the benchmark core independent from eBay and makes
the data snapshot reproducible.

Create a live source policy:

```bash
opennego market-source-policy \
  --output /tmp/ebay-live-source-policy.json \
  --source-id ebay_marketplace_insights \
  --adapter-kind ebay_marketplace_insights \
  --collection-mode official_api \
  --data-rights official_ebay_api_with_marketplace_insights_access \
  --terms-url https://developer.ebay.com/api-docs/buy/marketplace-insights/static/overview.html \
  --privacy-classification official_api_sold_comps_without_account_pii \
  --live-collection-enabled
```

Run with live credentials:

```bash
export EBAY_CLIENT_ID=...
export EBAY_CLIENT_SECRET=...

opennego ingest-ebay \
  --query "Apple iPhone 14 Pro 128GB Unlocked" \
  --source-policy /tmp/ebay-live-source-policy.json \
  --snapshot-output /tmp/ebay_sold_snapshot.json \
  --products-output /tmp/opennegotiation-products.json \
  --comps-output /tmp/opennegotiation-market-comps.json \
  --manifest-output /tmp/opennegotiation-market-dataset.json \
  --marketplace-id EBAY_US \
  --limit 50
```

For CI or local contract tests, pass `--mock-response` with a saved
Marketplace Insights JSON object. That path skips OAuth/network calls but still
requires a live source policy, parses the same response shape, and writes the
same normalized artifacts.

GCP is useful once we want hosted ingestion: Cloud Run or Cloud Scheduler for
bounded refresh jobs, Secret Manager for eBay credentials, GCS for sanitized
snapshots/manifests, and monitoring around quota failures. It is not a
substitute for eBay Marketplace Insights approval, and we should not deploy a
collector that bypasses official API or license boundaries.

Validate normalized fixtures before running a benchmark:

```bash
opennego validate-market \
  --products-file /tmp/opennego-products.json \
  --market-comps-file /tmp/opennego-market-comps.json \
  --manifest-file /tmp/opennego-market-dataset.json
```

The validator returns `opennego.market_validation.v1` JSON. It fails on
malformed products/comps, manifest count mismatches, price-summary median
mismatches, unsafe manifest privacy flags, and input hash mismatches when the
original source file is available. If artifacts were moved and the original
input path is unavailable, validation emits a warning instead of failing.

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
