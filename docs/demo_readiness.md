# Demo Readiness Audit

Updated: 2026-06-06

This audit answers the current readiness question for local demo surfaces,
architecture, CLI integration, and tests on `main`.

## Summary

The local fixture demo and the main user-centric workflow slices are implemented
on `main`: benchmark runs, policy-learning battle reports, strategy candidate
reruns, one-command training loops, local marketplace export, strategy
sparring, transaction settlement guards, config-level LLM agents,
provider-neutral profile LLM NPCs, and CLI loading for local user-agent
factories, plus offline sold-comps ingestion.
Offline ingested datasets can optionally write an aggregate dataset manifest
with input fingerprint and quality summaries, then validate those fixtures with
`opennego validate-market`.
The local fixture test suite also includes a shared workflow contract smoke for the
benchmark -> policy learning -> strategy candidate -> sparring rerun ->
comparison -> marketplace export loop.
Benchmark outputs can also be aggregated into a machine-readable leaderboard
with participant role-coverage summaries and buyer/seller role-track summaries.
One-command demo bundles can be validated independently with
`opennego validate-demo`.

A max-realism current-system OpenRouter validation was run on 2026-06-05 for
issue `#102`. Live provider execution remains optional and requires local
credentials, but both product modes were exercised with Keychain-supplied
credentials, 32-turn scenarios, 8192-token LLM calls, every current
`market_price_search` mode/visibility regime, all seller-side NPC profiles,
transaction guards, and full post-processing. Details are recorded in
`docs/live_validation_102.md`.

## Website / Demo Surfaces

Verified local fixture surfaces:

- `opennego demo --output-dir /tmp/opennego-readiness-demo --report /tmp/opennego-readiness-demo.html`
- `opennego spar --output-dir /tmp/opennego-readiness-sparring --report /tmp/opennego-readiness-sparring.html --opponent-profile seller_hardline_anchor_v1 --opponent-profile seller_hidden_fees_v1`
- `opennego train --output-dir /tmp/opennego-readiness-training --opponent-profile seller_hardline_anchor_v1 --parent-strategy-id buyer_baseline`

Browser smoke evidence:

- demo dashboard rendered Leaderboard Preview, Training / Prompt Optimization,
  Strategy Marketplace, Hardline Anchor Seller, and `buyer_overpaid_market`.
- Sparring report rendered OpenNegotiation strategy sparring report,
  `profile_backed_fixture_sparring`, Hardline Anchor Seller, Hidden Fees
  Seller, and `buyer_overpaid_market`.
- Both pages passed desktop 1280px and mobile 390px checks.
- No console errors were observed.
- No body-level horizontal overflow was observed.

Public website status:

- The public hosted website lives on the `web` branch and deploys through
  GitHub Pages at `https://kordi-ai.github.io/OpenNegotiation/`.
- The generated local static reports are still the canonical local fixture demo
  artifacts on `main`.

## Architecture

Implemented:

- Provider-neutral core environment through `AgentPort`, `LLMPort`, `ToolPort`,
  and `TransactionPort`.
- LiteLLM isolated behind `opennego.adapters`.
- Versioned benchmark artifacts for scenario, manifest, trace, and metrics.
- Policy-learning battle reports that read benchmark artifacts.
- Local NPC strategy registry and profile-backed local fixture sparring suite.
- Versioned strategy candidate generation, sparring reruns, and before/after
  comparison artifacts.
- One-command local fixture training loop that runs sparring, extracts a strategy
  candidate, applies it into a versioned strategy config, reruns the same
  profile, and compares before/after reports.
- External training adapter export and validation for handing strategy configs
  to user-owned agents without mutating arbitrary source code.
- Local strategy marketplace profile export, registry installation, and local fixture
  marketplace config validation.
- Local fixture role-swapped benchmark track with combined leaderboard role coverage.
- Config-runner custom `AgentPort` registration through Python API and explicit
  CLI local factory loading.
- Config-runner `llm_buyer` and `llm_seller` kinds behind injected `LLMPort`
  factories or CLI LiteLLM preflight.
- Profile-backed LLM NPC factory support through `LLMPort` for Python API
  sparring.
- CLI sparring support for LiteLLM-backed user agents through
  `--user-llm-model`; when paired with `--user-strategy`, the live user agent
  consumes the generated strategy candidate as additional strategy instructions.
- CLI LiteLLM profile NPC sparring through `--opponent-llm-model`, with
  explicit `--opponent-profile` selection required to bound live provider calls.
- Fixture transaction settlement guards for buyer all-in cost caps, seller
  net-revenue floors, shipping failure, item mismatch, return-window policy,
  and dispute-risk caps.
- Offline CSV/JSON sold-comps ingestion into `products.json`,
  `market_comps.json`, and optional aggregate dataset manifest artifacts.
- Real-market source policy generation and validation for source, licensing,
  privacy, credential, and anti-scraping boundaries before future live adapters.
- Market fixture validation CLI for products/comps plus optional dataset
  manifest consistency checks.
- Machine-readable leaderboard aggregation with ranked run rows, participant
  role-coverage summaries, and buyer/seller role-track summaries.
- Reciprocal `opennego arena-plan` methodology artifact for large-batch
  schedules, keeping deterministic scorecards primary and Elo/Bradley-Terry as
  optional future arena fitting.
- Artifact-backed leaderboard rendering in the static demo report when
  `leaderboard_summary.json` is present.
- Versioned `opennego.demo_bundle.v1` handoff manifest for one-command demo
  demo outputs.
- demo bundle validation CLI with schema drift, artifact existence, and
  workflow-order checks.
- One-command `opennego handoff` external package with package README,
  `opennego.external_handoff.v1` manifest, demo bundle validation, market fixture
  validation, marketplace validation, and role-swapped coverage artifacts.
- Shared local fixture workflow contract smoke covering benchmark artifacts, learning
  reports, strategy candidates, sparring reruns, comparison artifacts, and local
  marketplace export.
- Static HTML report generators for benchmark/demo and sparring surfaces.
- Architecture overview in `docs/architecture.md`.
- Python runtime declaration aligned to current syntax: Python 3.10+.

Guardrail:

- `tests/test_architecture_boundaries.py` checks that provider-specific imports
  do not leak into provider-neutral core modules.

Known architecture limits:

- CLI local agent loading is explicit only: no automatic module discovery,
  remote plugin installation, or hosted strategy execution.
- Strategy sparring defaults to deterministic fixture counterparties. Python API
  callers can supply custom user agents and profile-backed provider agents
  behind `LLMPort`; CLI users can opt into LiteLLM-backed user agents and
  profile NPCs with explicit `--opponent-profile` selections.
- Hosted marketplace backend, account-backed sharing, and provider-backed
  coaching are not implemented.
- Real-market evidence in the shipped demo remains fixture/offline-data backed.
  Offline sold-comps normalization is implemented, and the eBay Marketplace
  Insights adapter contract can write normalized fixtures with official API
  access. We have not yet production-verified it with approved eBay credentials,
  and non-eBay C2C marketplace collectors are not implemented.
- Transaction simulation validates deterministic settlement fees, lifecycle
  guard failures, and structured fixture terms for payment, logistics, returns,
  warranty, compliance, and dispute policy. Real payment, logistics, warranty,
  legal/compliance, and platform dispute provider integrations are not
  implemented.

## Tests And Static Checks

Verified commands:

```bash
pytest -q
PYTHONPYCACHEPREFIX=/tmp/opennego-pycache PYTHONPATH=src python3 -m compileall -q src tests
git diff --check
opennego validate-market --products-file examples/data/real_market_products.json --market-comps-file examples/data/real_market_comps.json
opennego market-source-policy --output "$tmpdir/source_policy.json" --source-id ebay_offline_export
opennego validate-market-source --policy "$tmpdir/source_policy.json"
opennego run --config "$tmpdir/full_realism_pair_gpt41mini_buyer_gpt41nano_seller.json"
opennego run --config "$tmpdir/full_realism_pair_gpt41nano_buyer_gpt41mini_seller.json"
opennego leaderboard --input-dir "$tmpdir/benchmark/combined" --output "$tmpdir/benchmark/leaderboard_summary.json"
opennego report --input-dir "$tmpdir/benchmark/combined" --output "$tmpdir/benchmark/full_realism_live_benchmark_report.html"
opennego spar --config "$tmpdir/full_realism_user_agent_sparring.json" --output-dir "$tmpdir/sparring/baseline" --opponent-profile seller_hardline_anchor_v1 --opponent-profile seller_stale_comps_v1 --opponent-profile seller_hidden_fees_v1 --user-llm-model openrouter/openai/gpt-4.1-mini --user-llm-max-tokens 8192 --opponent-llm-model openrouter/openai/gpt-4.1-nano --opponent-llm-max-tokens 8192 --learning-tool-regime symmetric_private_adversarial_market_search --no-fail-fast
opennego evolve --battle-report "$tmpdir/sparring/baseline/profiles/seller_hidden_fees_v1/battle_report.json" --output "$tmpdir/sparring/strategy_candidate.json" --parent-strategy-id full_realism_live_user_buyer_gpt41mini --iteration 1
opennego apply-strategy --candidate "$tmpdir/sparring/strategy_candidate.json" --output "$tmpdir/sparring/strategy_config.json" --strategy-id full_realism_live_user_buyer_gpt41mini_v1
opennego spar --config "$tmpdir/full_realism_user_agent_sparring.json" --output-dir "$tmpdir/sparring/rerun" --opponent-profile seller_hardline_anchor_v1 --opponent-profile seller_stale_comps_v1 --opponent-profile seller_hidden_fees_v1 --user-strategy "$tmpdir/sparring/strategy_candidate.json" --user-llm-model openrouter/openai/gpt-4.1-mini --user-llm-max-tokens 8192 --opponent-llm-model openrouter/openai/gpt-4.1-nano --opponent-llm-max-tokens 8192 --learning-tool-regime symmetric_private_adversarial_market_search --no-fail-fast
opennego compare --before "$tmpdir/sparring/baseline/profiles/seller_hardline_anchor_v1/battle_report.json" --after "$tmpdir/sparring/rerun/profiles/seller_hardline_anchor_v1/battle_report.json" --output "$tmpdir/sparring/comparison_seller_hardline_anchor_v1.json"
opennego compare --before "$tmpdir/sparring/baseline/profiles/seller_stale_comps_v1/battle_report.json" --after "$tmpdir/sparring/rerun/profiles/seller_stale_comps_v1/battle_report.json" --output "$tmpdir/sparring/comparison_seller_stale_comps_v1.json"
opennego compare --before "$tmpdir/sparring/baseline/profiles/seller_hidden_fees_v1/battle_report.json" --after "$tmpdir/sparring/rerun/profiles/seller_hidden_fees_v1/battle_report.json" --output "$tmpdir/sparring/comparison_seller_hidden_fees_v1.json"
opennego marketplace-export --candidate "$tmpdir/sparring/strategy_candidate.json" --output "$tmpdir/sparring/marketplace_profile.json" --profile-id full_realism_live_user_buyer_gpt41mini_iter1 --name "Full Realism Live User Buyer GPT-4.1 Mini Iteration 1" --summary "Strategy candidate extracted from the full-realism live OpenNegotiation pass across all seller NPC profiles." --difficulty custom --tag full-realism --tag live-validation --tag buyer --allowed-tool market_price_search --install-registry "$tmpdir/sparring/local_marketplace_registry.json" --overwrite
opennego validate-marketplace --registry "$tmpdir/sparring/local_marketplace_registry.json" --profile "$tmpdir/sparring/marketplace_profile.json"
opennego export-training-adapter --strategy-config "$tmpdir/sparring/strategy_config.json" --output "$tmpdir/sparring/training_adapter.json" --agent-kind litellm_user_agent --adapter-id full_realism_live_user_buyer_gpt41mini_adapter_v1
opennego validate-training-adapter --adapter "$tmpdir/sparring/training_adapter.json"
opennego demo --output-dir "$tmpdir/demo" --report "$tmpdir/demo.html"
opennego validate-demo --manifest "$tmpdir/demo/demo_manifest.json"
opennego handoff --output-dir "$tmpdir/handoff"
opennego train --output-dir "$tmpdir/training" --opponent-profile seller_hardline_anchor_v1 --parent-strategy-id buyer_baseline
opennego apply-strategy --candidate "$tmpdir/training/strategy_candidate.json" --output "$tmpdir/training/manual_strategy_config.json" --strategy-id buyer_baseline_manual_v1
opennego export-training-adapter --strategy-config "$tmpdir/training/strategy_config.json" --output "$tmpdir/training/external_training_adapter.json" --agent-kind buyer_baseline
opennego validate-training-adapter --adapter "$tmpdir/training/external_training_adapter.json"
opennego validate-marketplace --registry examples/data/npc_strategies.json
opennego role-swap --output-dir "$tmpdir/role_swap" --participant-id baseline_strategy
opennego arena-plan --participant model_a --participant model_b --participant model_c --scenario-id real_market_demo --seed 13 --output "$tmpdir/arena_plan.json"
secret-pattern scan for common provider key prefixes
```

Latest local result on this readiness branch:

- `pytest -q`: 154 passed.
- `compileall`: passing.
- `git diff --check`: passing.
- demo bundle validation smoke: passed with no errors or warnings.
- External handoff package smoke: passed and wrote
  `opennego.external_handoff.v1`.
- Product naming scan: public-facing copy uses OpenNegotiation; lowercase
  `opennego` remains only for package, CLI, schema, and generated-path
  compatibility contexts.
- Arena plan smoke: passed and wrote `opennego.arena_plan.v1`.
- Leaderboard duplicate-run regression: covered by tests; duplicate
  `manifest.run_id` values are rejected instead of being silently aggregated.
- Training loop smoke: passed and wrote `opennego.training_loop.v1` plus
  `opennego.strategy_config.v1`.
- Strategy application smoke: passed and wrote `opennego.strategy_config.v1`.
- External training adapter validation smoke: passed and wrote
  `opennego.external_training_adapter.v1`.
- Market source policy validation smoke: passed and wrote
  `opennego.market_source_policy.v1`.
- Marketplace validation smoke: curated registry and exported profile registry
  passed with no errors or warnings.
- Role-swapped benchmark smoke: passed with buyer/seller role coverage 1.0.
- Secret-pattern scan: no matches.

Current live provider status:

- OpenRouter credentials were supplied from local Keychain at command time.
- No API keys were written to the repository.
- Live traces and generated validation artifacts were kept in local `/tmp`
  outputs and were not committed.
- OpenRouter model catalog access succeeded; the validation used currently
  available low-cost model IDs.

Fresh max-realism live run summary for issue `#102`:

| Path | Models / profile | Result | Artifact evidence |
| --- | --- | --- | --- |
| Market gates | validated iPhone 14 Pro sold-comps fixture plus offline source policy | market and source-policy validation passed | `opennego.market_validation.v1`, `opennego.market_source_policy.v1`, `opennego.market_source_validation.v1` |
| Benchmark `opennego run --config` role-pair A/B | `gpt-4.1-mini` and `gpt-4.1-nano` swapped across buyer/seller roles | 24 completed, 0 failed across 12 tool regimes and 32-turn scenarios | per-run `manifest.json`, `scenario.json`, `trace.jsonl`, `metrics.json` |
| `opennego leaderboard` + `opennego report` | 24 live role-swapped runs | 24-run leaderboard generated; both participants have buyer/seller role coverage 1.0 | `leaderboard_summary.json`, HTML report |
| Baseline `opennego spar` | live user buyer `gpt-4.1-mini` vs live profile NPC seller `gpt-4.1-nano` across all seller NPC profiles | 3 profiles completed, 0 failed; 36 benchmark slices completed | `sparring_suite.json`, `battle_report.json`, HTML report |
| Strategy evolution rerun | worst baseline battle report -> candidate -> strategy config -> live user rerun with `--user-strategy` | 3 profiles completed, 0 failed; 36 rerun slices completed; profile scores improved by +12.5, +35.0, and +22.5 | `opennego.strategy_evolution.v1`, `opennego.strategy_config.v1`, `opennego.strategy_comparison.v1` |
| Marketplace / adapter | live-derived strategy candidate/config | marketplace validation and external adapter validation passed | `opennego.strategy_marketplace_profile.v1`, `opennego.external_training_adapter.v1` |

## Issue And PR Status

Current state:

- Current `main` includes the local backend workflow slices for benchmark,
  training, external strategy handoff, marketplace export, transaction guards,
  market source policy gates, offline data, and leaderboard artifacts.
- Open issue `#102` tracks the current full live workflow validation and web
  refresh.
- Open issue `#29` tracks remaining backend/product loop scale-up work.
- Public GitHub Pages hosting is active from the `web` branch. Earlier
  public-site polish work is superseded by the deployed OpenNegotiation site.
- There is no active stacked PR train for the current local demo path.

Readiness conclusion:

- Local fixture demo: implemented and verified.
- User-agent onboarding: Python API registration, CLI local factory loading,
  config LLM agents, and sparring custom user agents are implemented.
- Website/demo surfaces on `main`: implemented as static local reports and
  verified.
- Architecture: documented and guarded by tests.
- Tests: passing locally.
- Live provider validation: freshly verified with a max-realism current-system
  OpenRouter pass on issue `#102`; this is full workflow evidence for the
  current implementation, not a large-batch benchmark or a claim that live
  marketplace/payment/shipping integrations already exist.
- Hosted/public site: not complete until the GitHub Pages/private-repo blocker
  is resolved or another hosting target is selected.
