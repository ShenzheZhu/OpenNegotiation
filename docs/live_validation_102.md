# Issue #102 Live Validation

Date: 2026-06-05

This note records the stricter live validation pass for issue `#102`. The goal
was not another low-turn smoke run: model scope stayed small, while the data,
tool access, transaction settings, role coverage, and post-processing path were
kept realistic enough to exercise the current OpenNegotiation workflow.

## Validation Standard

- Models: two OpenRouter-backed models only, `openrouter/openai/gpt-4.1-mini`
  and `openrouter/openai/gpt-4.1-nano`.
- Turn budget: 8 turns per scenario.
- Generation budget: 512 tokens per LLM call.
- Data: validated offline real-market sold-comps fixture for an iPhone 14 Pro
  C2C scenario.
- Tool regimes:
  - `no_tools`
  - `buyer_private_market_search`
  - `seller_private_market_search`
  - `buyer_seller_private_market_search`
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
  --output /tmp/opennegotiation-realistic-102/policies/ebay_offline_export_policy.json \
  --source-id ebay_offline_export

opennego validate-market-source \
  --policy /tmp/opennegotiation-realistic-102/policies/ebay_offline_export_policy.json
```

Results:

- Market fixture validation: passed.
- Source policy validation: passed.
- Product count: 1.
- Comparable count: 3.
- Source boundary: offline/user-provided sold-comps fixture, not live scraping.

## Benchmark Mode

Two config-driven live A2A benchmark assignments were run:

| Assignment | Buyer | Seller | Runs | Failed |
| --- | --- | --- | --- | --- |
| A | `gpt-4.1-mini` | `gpt-4.1-nano` | 4 | 0 |
| B | `gpt-4.1-nano` | `gpt-4.1-mini` | 4 | 0 |

Each assignment covered the four tool regimes listed above.

Observed outcomes:

| Assignment | Tool regime | Outcome | Deal price | Completed turns |
| --- | --- | --- | --- | --- |
| A | `no_tools` | deal, transaction failed seller-net guard | 520 | 5 |
| A | `buyer_private_market_search` | deal | 607 | 8 |
| A | `seller_private_market_search` | rejected | n/a | 6 |
| A | `buyer_seller_private_market_search` | deal | 590 | 4 |
| B | `no_tools` | deal | 610 | 3 |
| B | `buyer_private_market_search` | deal | 540 | 3 |
| B | `seller_private_market_search` | deal | 650 | 4 |
| B | `buyer_seller_private_market_search` | deal | 575 | 5 |

Post-processing:

```bash
opennego leaderboard \
  --input-dir /tmp/opennegotiation-realistic-102/benchmark/combined \
  --output /tmp/opennegotiation-realistic-102/benchmark/leaderboard_summary.json

opennego report \
  --input-dir /tmp/opennegotiation-realistic-102/benchmark/combined \
  --output /tmp/opennegotiation-realistic-102/benchmark/realistic_live_benchmark_report.html
```

Results:

- Leaderboard run count: 8.
- Both models had buyer and seller role coverage `1.0`.
- Participant summaries and buyer/seller role tracks were generated.
- Report HTML was generated from the combined benchmark artifacts.

## Sparring / Evolution Mode

The user-agent workflow used:

- User role: buyer.
- Live user agent: `openrouter/openai/gpt-4.1-mini`.
- NPC counterparty profile: `seller_stale_comps_v1`.
- Live profile NPC model: `openrouter/openai/gpt-4.1-nano`.
- Learning regime: `buyer_seller_private_market_search`.

Baseline sparring:

- Completed profiles: 1.
- Failed profiles: 0.
- Underlying benchmark slices: 4 completed, 0 failed.
- Battle report outcome: rejected.
- Policy score: 50.0.
- Failure modes: `deal_failure`, `tool_use`.
- Lessons: `no_deal_recovery`, `missed_market_tool`.

Evolution and rerun:

```bash
opennego evolve \
  --battle-report /tmp/opennegotiation-realistic-102/sparring_after_fix/baseline/profiles/seller_stale_comps_v1/battle_report.json \
  --output /tmp/opennegotiation-realistic-102/sparring_after_fix/strategy_candidate.json \
  --parent-strategy-id live_user_buyer_gpt41mini \
  --iteration 1

opennego apply-strategy \
  --candidate /tmp/opennegotiation-realistic-102/sparring_after_fix/strategy_candidate.json \
  --output /tmp/opennegotiation-realistic-102/sparring_after_fix/strategy_config.json \
  --strategy-id live_user_buyer_gpt41mini_v1

opennego spar \
  --config /tmp/opennegotiation-realistic-102/configs/realistic_user_agent_sparring.json \
  --output-dir /tmp/opennegotiation-realistic-102/sparring_after_fix/rerun \
  --report /tmp/opennegotiation-realistic-102/sparring_after_fix/rerun_sparring_report.html \
  --opponent-profile seller_stale_comps_v1 \
  --user-strategy /tmp/opennegotiation-realistic-102/sparring_after_fix/strategy_candidate.json \
  --user-llm-model openrouter/openai/gpt-4.1-mini \
  --user-llm-max-tokens 512 \
  --opponent-llm-model openrouter/openai/gpt-4.1-nano \
  --opponent-llm-max-tokens 512 \
  --learning-tool-regime buyer_seller_private_market_search \
  --no-fail-fast

opennego compare \
  --before /tmp/opennegotiation-realistic-102/sparring_after_fix/baseline/profiles/seller_stale_comps_v1/battle_report.json \
  --after /tmp/opennegotiation-realistic-102/sparring_after_fix/rerun/profiles/seller_stale_comps_v1/battle_report.json \
  --output /tmp/opennegotiation-realistic-102/sparring_after_fix/strategy_comparison.json
```

Results:

- Strategy candidate generated: `opennego.strategy_evolution.v1`.
- Strategy config generated: `opennego.strategy_config.v1`.
- Rerun completed: 1 profile, 4 benchmark slices, 0 failures.
- Rerun manifest recorded `user_strategy.enabled=true`.
- Rerun manifest recorded `transaction.enabled=true`.
- Comparison result: score 50.0 -> 50.0, delta `0.0`, summary
  `Strategy unchanged`.

The evolution path is therefore executable and traceable, but this single-step
deterministic patch did not improve the live policy in this scenario. That is a
product limitation, not an execution failure.

## Marketplace And Adapter

Validated commands:

```bash
opennego marketplace-export \
  --candidate /tmp/opennegotiation-realistic-102/sparring_after_fix/strategy_candidate.json \
  --output /tmp/opennegotiation-realistic-102/sparring_after_fix/marketplace_profile.json \
  --profile-id live_user_buyer_gpt41mini_iter1 \
  --name "Live User Buyer GPT-4.1 Mini Iteration 1" \
  --summary "Strategy candidate extracted from a strict live OpenNegotiation sparring pass against Stale Comps Seller." \
  --difficulty custom \
  --tag live-validation \
  --tag buyer \
  --allowed-tool market_price_search \
  --install-registry /tmp/opennegotiation-realistic-102/sparring_after_fix/local_marketplace_registry.json \
  --overwrite

opennego validate-marketplace \
  --registry /tmp/opennegotiation-realistic-102/sparring_after_fix/local_marketplace_registry.json \
  --profile /tmp/opennegotiation-realistic-102/sparring_after_fix/marketplace_profile.json

opennego export-training-adapter \
  --strategy-config /tmp/opennegotiation-realistic-102/sparring_after_fix/strategy_config.json \
  --output /tmp/opennegotiation-realistic-102/sparring_after_fix/training_adapter.json \
  --agent-kind litellm_user_agent \
  --adapter-id live_user_buyer_gpt41mini_adapter_v1

opennego validate-training-adapter \
  --adapter /tmp/opennegotiation-realistic-102/sparring_after_fix/training_adapter.json
```

Results:

- Marketplace validation: passed.
- External training adapter validation: passed.
- Sparring/evolution after-fix artifacts: 8 manifests, 8 metrics files, and
  8 trace files.

## Bug Found And Fixed

The live artifact audit found that benchmark manifests recorded transaction
metadata, but sparring manifests did not, even though sparring used the same
transaction simulator and metrics included transaction fields.

Fix:

- Added a reusable transaction metadata helper in `opennego.runner`.
- Updated `opennego.sparring` so sparring run manifests include both config
  metadata and transaction metadata.
- Added a workflow contract regression assertion that sparring manifests retain
  transaction provenance.

## Current Limits

- Real-market evidence is still fixture/offline-export backed. Live eBay or
  C2C marketplace ingestion is not implemented.
- The current training loop extracts deterministic strategy patches and reruns
  the agent, but it does not yet run a multi-iteration optimizer, versioned
  strategy selection, or automatic model-policy improvement.
- The local marketplace is a JSON registry and validator, not a hosted
  account-backed marketplace.
- Transaction simulation is deterministic fixture settlement, not an integration
  with real payment, shipping, warranty, compliance, or dispute providers.
- This is a strict small-scope validation pass, not a large-batch benchmark.
