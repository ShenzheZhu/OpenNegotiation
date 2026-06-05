# MVP Readiness Audit

Date: 2026-06-05

This audit answers the current readiness question for local demo surfaces,
architecture, CLI integration, and tests on `main`.

## Summary

The no-key local MVP and the main user-centric workflow slices are implemented
on `main`: benchmark runs, policy-learning battle reports, strategy candidate
reruns, one-command training loops, local marketplace export, strategy
sparring, transaction settlement guards, config-level LLM agents,
provider-neutral profile LLM NPCs, and CLI loading for local user-agent
factories, plus offline sold-comps ingestion.
Offline ingested datasets can optionally write an aggregate dataset manifest
with input fingerprint and quality summaries, then validate those fixtures with
`opennego validate-market`.
The no-key test suite also includes a shared workflow contract smoke for the
benchmark -> policy learning -> strategy candidate -> sparring rerun ->
comparison -> marketplace export loop.
Benchmark outputs can also be aggregated into a machine-readable leaderboard
with participant role-coverage summaries and buyer/seller role-track summaries.
One-command MVP demo bundles can be validated independently with
`opennego validate-demo-bundle`.

A fresh bounded OpenRouter validation was run on 2026-06-05 for issue `#100`.
Live provider execution remains an optional demo path that requires local
credentials, but the current LiteLLM/OpenRouter paths were exercised with
Keychain-supplied credentials and low turn/token budgets.

## Website / Demo Surfaces

Verified no-key surfaces:

- `opennego mvp-demo --output-dir /tmp/opennego-readiness-mvp --report /tmp/opennego-readiness-mvp.html`
- `opennego spar --output-dir /tmp/opennego-readiness-sparring --report /tmp/opennego-readiness-sparring.html --opponent-profile seller_hardline_anchor_v1 --opponent-profile seller_hidden_fees_v1`
- `opennego train --output-dir /tmp/opennego-readiness-training --opponent-profile seller_hardline_anchor_v1 --parent-strategy-id buyer_baseline`

Browser smoke evidence:

- MVP dashboard rendered Leaderboard Preview, Training / Prompt Optimization,
  Strategy Marketplace, Hardline Anchor Seller, and `buyer_overpaid_market`.
- Sparring report rendered OpenNegotiation strategy sparring report,
  `profile_backed_fixture_sparring`, Hardline Anchor Seller, Hidden Fees
  Seller, and `buyer_overpaid_market`.
- Both pages passed desktop 1280px and mobile 390px checks.
- No console errors were observed.
- No body-level horizontal overflow was observed.

Not complete:

- The public hosted website work lives on the `web` branch. GitHub Pages
  configuration is blocked while the repository/private-plan combination does
  not support Pages for this repo.
- The generated local static reports are still the canonical no-key demo
  artifacts on `main`.

## Architecture

Implemented:

- Provider-neutral core environment through `AgentPort`, `LLMPort`, `ToolPort`,
  and `TransactionPort`.
- LiteLLM isolated behind `opennego.adapters`.
- Versioned benchmark artifacts for scenario, manifest, trace, and metrics.
- Policy-learning battle reports that read benchmark artifacts.
- Local NPC strategy registry and profile-backed no-key sparring suite.
- Versioned strategy candidate generation, sparring reruns, and before/after
  comparison artifacts.
- One-command no-key training loop that runs sparring, extracts a strategy
  candidate, applies it into a versioned strategy config, reruns the same
  profile, and compares before/after reports.
- External training adapter export and validation for handing strategy configs
  to user-owned agents without mutating arbitrary source code.
- Local strategy marketplace profile export, registry installation, and no-key
  marketplace config validation.
- No-key role-swapped benchmark track with combined leaderboard role coverage.
- Config-runner custom `AgentPort` registration through Python API and explicit
  CLI local factory loading.
- Config-runner `llm_buyer` and `llm_seller` kinds behind injected `LLMPort`
  factories or CLI LiteLLM preflight.
- Profile-backed LLM NPC factory support through `LLMPort` for Python API
  sparring.
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
- Versioned `opennego.mvp_demo_bundle.v1` handoff manifest for one-command MVP
  demo outputs.
- MVP demo bundle validation CLI with schema drift, artifact existence, and
  workflow-order checks.
- One-command `opennego handoff` external package with package README,
  `opennego.external_handoff.v1` manifest, MVP bundle validation, market fixture
  validation, marketplace validation, and role-swapped coverage artifacts.
- Shared no-key workflow contract smoke covering benchmark artifacts, learning
  reports, strategy candidates, sparring reruns, comparison artifacts, and local
  marketplace export.
- Static HTML report generators for benchmark/MVP and sparring surfaces.
- Architecture overview in `docs/architecture.md`.
- Python runtime declaration aligned to current syntax: Python 3.10+.

Guardrail:

- `tests/test_architecture_boundaries.py` checks that provider-specific imports
  do not leak into provider-neutral core modules.

Known architecture limits:

- CLI local agent loading is explicit only: no automatic module discovery,
  remote plugin installation, or hosted strategy execution.
- Strategy sparring defaults to deterministic fixture counterparties. Python API
  callers can supply profile-backed provider agents behind `LLMPort`, and CLI
  users can opt into LiteLLM-backed profile NPCs with explicit
  `--opponent-profile` selections.
- Hosted marketplace backend, account-backed sharing, and provider-backed
  coaching are not implemented.
- Real-market evidence remains fixture/offline-data backed. Offline sold-comps
  normalization is implemented; live eBay or C2C marketplace collection is not
  implemented.
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
opennego run-models --output-dir /tmp/opennego-live-five-fixed-20260605 --max-turns 3 --max-tokens 220
opennego mvp-demo --output-dir "$tmpdir/mvp" --report "$tmpdir/mvp.html"
opennego validate-demo-bundle --manifest "$tmpdir/mvp/mvp_demo_manifest.json"
opennego handoff --output-dir "$tmpdir/handoff"
opennego train --output-dir "$tmpdir/training" --opponent-profile seller_hardline_anchor_v1 --parent-strategy-id buyer_baseline
opennego apply-strategy --candidate "$tmpdir/training/strategy_candidate.json" --output "$tmpdir/training/manual_strategy_config.json" --strategy-id buyer_baseline_manual_v1
opennego export-training-adapter --strategy-config "$tmpdir/training/strategy_config.json" --output "$tmpdir/training/external_training_adapter.json" --agent-kind buyer_baseline
opennego validate-training-adapter --adapter "$tmpdir/training/external_training_adapter.json"
opennego market-source-policy --output "$tmpdir/source_policy.json" --source-id ebay_offline_export
opennego validate-market-source --policy "$tmpdir/source_policy.json"
opennego validate-marketplace --registry examples/data/npc_strategies.json
opennego role-swap --output-dir "$tmpdir/role_swap" --participant-id baseline_strategy
opennego arena-plan --participant model_a --participant model_b --participant model_c --scenario-id real_market_demo --seed 13 --output "$tmpdir/arena_plan.json"
secret-pattern scan for common provider key prefixes
```

Latest local result on this readiness branch:

- `pytest -q`: 138 passed.
- `compileall`: passing.
- `git diff --check`: passing.
- MVP demo bundle validation smoke: passed with no errors or warnings.
- External handoff package smoke: passed and wrote
  `opennego.external_handoff.v1`.
- Product naming scan: public-facing copy uses OpenNegotiation; lowercase
  `opennego` remains only for package, CLI, schema, and generated-path
  compatibility contexts.
- Arena plan smoke: passed and wrote `opennego.arena_plan.v1`.
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

Fresh live run summary for issue `#100`:

| Path | Models / profile | Result | Artifact evidence |
| --- | --- | --- | --- |
| `opennego run-models` | `openrouter/openai/gpt-4.1-nano`, `openrouter/openai/gpt-4.1-mini` | 2 completed, 0 failed; both reached deals | `summary.json`, per-run `manifest.json`, `scenario.json`, `trace.jsonl`, `metrics.json`, leaderboard JSON, HTML report |
| `opennego run --config` | live `llm_buyer` + live `llm_seller` using `openrouter/openai/gpt-4.1-nano` | 1 completed, 0 failed; timeout outcome after 2 turns | benchmark artifacts plus HTML report |
| `opennego spar` | `seller_hardline_anchor_v1` as `litellm_profile_npc:openrouter/openai/gpt-4.1-nano` | 1 profile completed, 0 failed; 3 benchmark slices completed | `sparring_suite.json`, `battle_report.json`, HTML report |
| Strategy evolution | live sparring `battle_report.json` | candidate and strategy config generated | `opennego.strategy_evolution.v1`, `opennego.strategy_config.v1` |
| Marketplace / adapter | live-derived strategy candidate/config | marketplace validation and external adapter validation passed | `opennego.strategy_marketplace_profile.v1`, `opennego.external_training_adapter.v1` |

## Issue And PR Status

Current state:

- Current `main` includes the local backend workflow slices for benchmark,
  training, external strategy handoff, marketplace export, transaction guards,
  market source policy gates, offline data, and leaderboard artifacts.
- Open issue `#29` tracks remaining backend/product loop scale-up work.
- Open issue `#28` tracks public GitHub Pages hosting and remains blocked by
  repository/private-plan support for Pages.
- There is no active stacked PR train for the current local MVP path.

Readiness conclusion:

- No-key local MVP: implemented and verified.
- User-agent onboarding: Python API registration, CLI local factory loading,
  config LLM agents, and sparring custom user agents are implemented.
- Website/demo surfaces on `main`: implemented as static local reports and
  verified.
- Architecture: documented and guarded by tests.
- Tests: passing locally.
- Live provider smoke: freshly verified with bounded OpenRouter runs on issue
  `#100`; this is smoke evidence, not a batch benchmark.
- Hosted/public site: not complete until the GitHub Pages/private-repo blocker
  is resolved or another hosting target is selected.
