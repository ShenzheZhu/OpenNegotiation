# GitHub Actions Market Ingestion

OpenNegotiation can run the eBay sold-comps ingestion adapter from GitHub
Actions on a manual or scheduled trigger. This path is useful when GCP Secret
Manager IAM is not available yet: eBay credentials live in GitHub Actions
Secrets, and each run publishes a frozen market artifact bundle as a GitHub
Actions artifact.

This is not a public live market-data server. It is a scheduled artifact
producer. Benchmark and training runs should consume the frozen `products.json`,
`market_comps.json`, and `market_manifest.json` outputs.

## Workflow

Workflow file:

```text
.github/workflows/market-ingestion.yml
```

Triggers:

- manual `workflow_dispatch`
- weekly schedule at Monday 09:00 UTC

Required repository secrets:

- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`

Default parameters:

- query: `Apple iPhone 14 Pro 128GB Unlocked`
- marketplace id: `EBAY_US`
- limit: `50`

Manual runs can override query, marketplace id, and limit.

## Output Bundle

Each successful run uploads a GitHub artifact named like:

```text
ebay-market-artifacts-<query-slug>-<timestamp>-<github-run-id>
```

Bundle contents:

- `ebay-live-source-policy.json`
- `ebay_sold_snapshot.json`
- `products.json`
- `market_comps.json`
- `market_manifest.json`
- `market_validation.json`
- `manifest-pointer.json`

The workflow fails closed if eBay credentials are missing, source-policy
validation fails, eBay access is denied, no sold-comps records are returned, or
normalized market validation fails. It does not fall back to fixture data.

## GCS Later

The v0 workflow intentionally does not upload to GCS because that still requires
GitHub-to-GCP authentication. Add that later with Workload Identity Federation
or a tightly scoped service-account credential once the project owner can grant
the required IAM bindings.
