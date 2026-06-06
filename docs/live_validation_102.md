# Issue #102 Live Validation

Date: 2026-06-05

This note records the max-realism live validation pass for issue `#102`.
It supersedes the earlier 8-turn / 512-token pass from PR `#112`, which was
useful for finding a sparring provenance bug but was still too demo-like for
acceptance.

The target here is current-system max realism: small model scope, but the
runtime budget, tool regimes, transaction terms, NPC set, and post-processing
surface are not demo-reduced.

## Validation Standard

- Models: two OpenRouter-backed models, `openrouter/openai/gpt-4.1-mini` and
  `openrouter/openai/gpt-4.1-nano`.
- Turn budget: 32 public turns per scenario. The environment still allows
  private tool-call steps up to `max_turns * 4`, so each run can spend extra
  private steps gathering evidence.
- Generation budget: 8192 output tokens per LLM call.
- Data: validated offline real-market sold-comps fixture for an iPhone 14 Pro
  C2C scenario.
- Tool surface: every current `market_price_search` regime used by this pass:
  - `no_tools`
  - `buyer_private_clean_market_search`
  - `seller_private_clean_market_search`
  - `symmetric_private_clean_market_search`
  - `symmetric_public_clean_market_search`
  - `buyer_private_noisy_market_search`
  - `symmetric_private_noisy_market_search`
  - `buyer_private_stale_market_search`
  - `symmetric_private_stale_market_search`
  - `buyer_private_adversarial_market_search`
  - `symmetric_private_adversarial_market_search`
  - `symmetric_private_failure_market_search`
- NPC surface: all seller-side NPC profiles in the current registry:
  `seller_hardline_anchor_v1`, `seller_stale_comps_v1`, and
  `seller_hidden_fees_v1`.
- Transaction layer: fixture settlement with shipping, tax, escrow,
  payment fee, seller fee, return risk, reputation risk, dispute risk, buyer
  all-in cap, seller net-revenue floor, tracking, delivery SLA, returns,
  warranty, compliance, and dispute policy metadata.
- Credential handling: OpenRouter credentials were read from local Keychain and
  injected only into child-process environment variables. No credentials or raw
  live artifacts were committed.

## Data And Source Gates

Validated commands:

```bash
opennego validate-market \
  --products-file examples/data/real_market_products.json \
  --market-comps-file examples/data/real_market_comps.json

opennego market-source-policy \
  --output /tmp/opennegotiation-full-realism-102/policies/ebay_offline_export_policy.json \
  --source-id ebay_offline_export

opennego validate-market-source \
  --policy /tmp/opennegotiation-full-realism-102/policies/ebay_offline_export_policy.json
```

Results:

- Market fixture validation: passed.
- Source policy validation: passed.
- Product count: 1.
- Comparable count: 3.
- Source boundary: offline/user-provided sold-comps fixture, not live scraping.

## Benchmark Mode

Two config-driven live A2A benchmark assignments were run:

| Assignment | Buyer | Seller | Tool regimes | Runs | Failed |
| --- | --- | --- | --- | --- | --- |
| A | `gpt-4.1-mini` | `gpt-4.1-nano` | 12 | 12 | 0 |
| B | `gpt-4.1-nano` | `gpt-4.1-mini` | 12 | 12 | 0 |

Post-processing:

```bash
opennego leaderboard \
  --input-dir /tmp/opennegotiation-full-realism-102/benchmark/combined \
  --output /tmp/opennegotiation-full-realism-102/benchmark/leaderboard_summary.json

opennego report \
  --input-dir /tmp/opennegotiation-full-realism-102/benchmark/combined \
  --output /tmp/opennegotiation-full-realism-102/benchmark/full_realism_live_benchmark_report.html
```

Results:

- Benchmark execution: 24 completed, 0 failed.
- Leaderboard run count: 24.
- Both models had buyer and seller role coverage `1.0`.
- `gpt-4.1-mini` average score: `83.7375`.
- `gpt-4.1-nano` average score: `83.7375`.
- Buyer track deal rates:
  - `gpt-4.1-nano`: `0.8333`
  - `gpt-4.1-mini`: `0.9167`
- Buyer track transaction completion rates:
  - `gpt-4.1-nano`: `0.8333`
  - `gpt-4.1-mini`: `0.5833`
- Tool failure surfaced in the leaderboard: one role track had tool failure rate
  `0.1`.
- The 24-run benchmark report rendered successfully.

This pass is materially different from the earlier smoke runs: it includes
public tools, private tools, clean/noisy/stale/adversarial/failure tool modes,
role swapping, transaction guard failures, and full leaderboard/report
post-processing.

## Sparring / Evolution Mode

Baseline setup:

- User role: buyer.
- Live user agent: `openrouter/openai/gpt-4.1-mini`.
- Live profile NPC model: `openrouter/openai/gpt-4.1-nano`.
- Opponent profiles: all seller-side registry profiles.
- Learning regime: `symmetric_private_adversarial_market_search`.
- Runtime: 32 turns, 8192 output tokens per LLM call, 12 tool regimes per
  profile.

Baseline results:

| Profile | Benchmark slices | Failed | Outcome | Policy score | Lessons |
| --- | --- | --- | --- | --- | --- |
| `seller_hardline_anchor_v1` | 12 | 0 | rejected | 50.0 | `no_deal_recovery`, `missed_market_tool` |
| `seller_stale_comps_v1` | 12 | 0 | invalid_accept | 50.0 | `no_deal_recovery`, `missed_market_tool` |
| `seller_hidden_fees_v1` | 12 | 0 | rejected | 37.5 | `no_deal_recovery`, `missed_market_tool`, `opponent_trap_awareness` |

The strategy candidate was generated from the weakest baseline profile,
`seller_hidden_fees_v1`, then applied to the live user agent for a rerun across
all three seller NPC profiles.

Applied lessons:

- `no_deal_recovery`
- `missed_market_tool`
- `opponent_trap_awareness`

Applied strategy patches:

- Switch from exploration to close mode near turn exhaustion.
- Search recent sold comps before the first offer and use median/IQR anchors.
- Classify the opponent tactic before responding and apply a named
  countermeasure.

Rerun results:

| Profile | Benchmark slices | Failed | Outcome | Deal price | Policy score |
| --- | --- | --- | --- | --- | --- |
| `seller_hardline_anchor_v1` | 12 | 0 | rejected | n/a | 62.5 |
| `seller_stale_comps_v1` | 12 | 0 | deal | 610 | 85.0 |
| `seller_hidden_fees_v1` | 12 | 0 | deal | 680 | 60.0 |

Profile-by-profile comparisons:

| Profile | Before | After | Delta |
| --- | --- | --- | --- |
| `seller_hardline_anchor_v1` | 50.0 | 62.5 | +12.5 |
| `seller_stale_comps_v1` | 50.0 | 85.0 | +35.0 |
| `seller_hidden_fees_v1` | 37.5 | 60.0 | +22.5 |

The evolution loop is therefore executable and traceable under the full current
surface, and this specific candidate improved all three seller-NPC comparison
scores. It did not solve every case: hardline still ended rejected, and the
hidden-fees rerun still surfaced price-discipline and transaction-risk lessons.

## Marketplace And Adapter

Validated commands:

```bash
opennego marketplace-export \
  --candidate /tmp/opennegotiation-full-realism-102/sparring/strategy_candidate.json \
  --output /tmp/opennegotiation-full-realism-102/sparring/marketplace_profile.json \
  --profile-id full_realism_live_user_buyer_gpt41mini_iter1 \
  --name "Full Realism Live User Buyer GPT-4.1 Mini Iteration 1" \
  --summary "Strategy candidate extracted from the full-realism live OpenNegotiation pass across all seller NPC profiles." \
  --difficulty custom \
  --tag full-realism \
  --tag live-validation \
  --tag buyer \
  --allowed-tool market_price_search \
  --install-registry /tmp/opennegotiation-full-realism-102/sparring/local_marketplace_registry.json \
  --overwrite

opennego validate-marketplace \
  --registry /tmp/opennegotiation-full-realism-102/sparring/local_marketplace_registry.json \
  --profile /tmp/opennegotiation-full-realism-102/sparring/marketplace_profile.json

opennego export-training-adapter \
  --strategy-config /tmp/opennegotiation-full-realism-102/sparring/strategy_config.json \
  --output /tmp/opennegotiation-full-realism-102/sparring/training_adapter.json \
  --agent-kind litellm_user_agent \
  --adapter-id full_realism_live_user_buyer_gpt41mini_adapter_v1

opennego validate-training-adapter \
  --adapter /tmp/opennegotiation-full-realism-102/sparring/training_adapter.json
```

Results:

- Marketplace validation: passed.
- External training adapter validation: passed.
- Executed live slices: 96 total.
  - 24 benchmark role-swap slices.
  - 36 baseline sparring slices.
  - 36 strategy-rerun sparring slices.
- The temporary output tree contains 120 manifest/metrics/trace triplets because
  the benchmark report aggregation also creates a 24-run combined copy.

## Bug Found In Previous Pass

The previous 8-turn / 512-token pass found that benchmark manifests recorded
transaction metadata, but sparring manifests did not, even though sparring used
the same transaction simulator and metrics included transaction fields.

Fix shipped in PR `#112`:

- Added a reusable transaction metadata helper in `opennego.runner`.
- Updated `opennego.sparring` so sparring run manifests include both config
  metadata and transaction metadata.
- Added a workflow contract regression assertion that sparring manifests retain
  transaction provenance.

The full-realism pass above was run after that fix.

## Current Limits

- Real-market evidence in this validation run is still fixture/offline-export
  backed. The eBay Marketplace Insights adapter contract now exists for
  official sold-comps ingestion, but this run did not use approved eBay
  production credentials and did not validate non-eBay C2C collectors.
- The current tool surface is still one provider-neutral market search tool with
  multiple modes. Search, provenance, escrow, payment, shipping, dispute, and
  marketplace providers are not separate live integrations yet.
- The local marketplace is a JSON registry and validator, not a hosted
  account-backed marketplace.
- Transaction simulation is deterministic fixture settlement, not an integration
  with real payment, shipping, warranty, compliance, or dispute providers.
- This is max-realism coverage of the current implementation, not a large-batch
  leaderboard benchmark and not a claim that real-world marketplace integrations
  already exist.
