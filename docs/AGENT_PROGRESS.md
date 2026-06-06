# Agent Progress Log

This file tracks concrete engineering progress during the OpenNegotiation bootstrap.
Do not record API keys, cookies, credentials, or raw live-provider payloads here.

## 2026-06-05

### Completed

- Bootstrapped a fixture-backed real-market demo around a used iPhone product
  cluster.
- Added market-reference schema and metrics so C2C scenarios can be scored
  against sold-comparable anchors instead of pretending seller cost is observed.
- Added a static HTML report generator with an OpenNegotiation overview, mechanism,
  why-choose-us cards, leaderboard preview, key findings, and trace replay.
- Added `opennego report` for rendering versioned artifacts into the demo panel.
- Added `opennego run-models` for a small five-model live demo path.
- Added no-key tests for model-demo artifact generation with fake LLMs.
- Added model-demo `summary.json` and redacted per-model `failure.json`
  artifacts for live-provider failure auditability.
- Added a live-model attempt-status table to the static report when
  `summary.json` is present.
- Selected a high-quality OpenRouter-backed five-model default set for the
  demo: GPT-5.4 Pro, Claude Opus 4.8, Gemini 3.1 Pro Preview, Grok 4.3, and
  Qwen3 235B A22B.
- Added the first no-key policy-learning demo slice: NPC strategy registry,
  `opennego strategies`, `opennego learn`, battle-report JSON, and
  trace-grounded strategy prompt patches.
- Integrated policy-learning reports and NPC strategy profiles into the static
  HTML demo report.
- Added `examples/reports/full_demo.html` as the curated local demo
  page covering benchmark, training/prompt optimization, and strategy
  marketplace.
- Added `opennego demo` as the one-command no-key flow for generating the
  benchmark artifacts, leaderboard summary, bundle manifest, battle report, and
  demo HTML page.
- Added `opennego spar` as a no-key strategy sparring suite that runs selected
  marketplace NPC profiles through fixture-backed battle-report diagnostics.
- Added `opennego spar --report` for rendering a compact static HTML report
  from `sparring_suite.json`.
- Added profile-backed sparring where NPC strategy profiles are instantiated as
  actual deterministic buyer/seller counterparties in traces and manifests.
- Added versioned strategy candidates, candidate-backed sparring reruns, and
  before/after strategy comparison artifacts.
- Added Python API custom agent registration for the config runner and sparring
  suite.
- Added local marketplace profile export from strategy candidates, including
  optional registry installation.
- Added deterministic transaction settlement guards for buyer all-in cost caps
  and seller net-revenue floors.
- Added deterministic transaction lifecycle guards for shipping failure, item
  mismatch, return-window policy, and dispute-risk caps.
- Added structured fixture transaction terms for payment, logistics, returns,
  warranty, compliance, and dispute policy metadata, plus deterministic delivery
  SLA, warranty-window, and compliance guards.
- Added profile-backed LLM NPC factories behind `LLMPort` for Python API
  sparring.
- Added config-runner `llm_buyer` and `llm_seller` agent kinds behind
  provider-neutral `LLMPort` factories and CLI LiteLLM preflight.
- Added explicit CLI local agent factory loading for benchmark configs and
  sparring user agents.
- Added offline sold-comps CSV/JSON ingestion into normalized product clusters
  and market-comparable fixture files.
- Added optional aggregate market dataset manifests for offline sold-comps
  ingestion, including input fingerprints and quality summaries.
- Added real-market source policy artifacts and validation gates for adapter
  readiness, including collection-mode, data-rights, privacy, credentials, and
  anti-scraping boundaries.
- Added an eBay Marketplace Insights adapter contract and `opennego ingest-ebay`
  command. It supports no-key mock-response tests and live official-API
  ingestion when eBay credentials and Marketplace Insights access are available.
- Added a scheduled/manual GitHub Actions market-ingestion workflow that reads
  eBay credentials from repository secrets and publishes frozen validated market
  artifact bundles as GitHub Actions artifacts.
- Added `opennego validate-market` for no-key product, comparable, and dataset
  manifest consistency checks.
- Added `opennego leaderboard` for machine-readable run rankings, participant
  role-coverage summaries, and buyer/seller role-track scorecard aggregation.
- Added artifact-backed leaderboard rendering to `opennego report` when
  `leaderboard_summary.json` is present.
- Added `opennego.demo_bundle.v1` as a durable manifest for one-command demo
  demo artifact handoff.
- Added `opennego validate-demo` for no-key demo bundle release checks
  across manifest schema, artifact existence, workflow order, and artifact
  schema versions.
- Added `opennego handoff` for a one-command external no-key package with
  package README, demo artifacts, validation JSON, role-swapped artifacts, and
  `opennego.external_handoff.v1` manifest.
- Added a shared no-key workflow contract smoke for benchmark artifacts,
  leaderboard summaries, artifact-backed reports, battle reports, strategy
  candidates, sparring reruns, comparison artifacts, and local marketplace
  export.
- Added CLI LiteLLM profile NPC sparring with explicit opponent-profile
  selection and no-key fake-gateway tests.
- Added CLI LiteLLM user-agent sparring with `--user-llm-model`; the live user
  agent can consume a generated `--user-strategy` candidate during reruns.
- Added `opennego train` as a one-command no-key training loop for baseline
  sparring, strategy extraction, candidate rerun, and before/after comparison.
- Added `opennego apply-strategy` for applying strategy candidates into
  versioned `opennego.strategy_config.v1` artifacts with fixed-base/editable
  strategy prompt-layer metadata.
- Added `opennego export-training-adapter` and
  `opennego validate-training-adapter` for external user-agent strategy config
  handoff without arbitrary source-code mutation.
- Added `opennego validate-marketplace` for local strategy registry and shared
  marketplace profile release checks.
- Added `opennego role-swap` for a small no-key role-swapped benchmark track
  with combined leaderboard role coverage.
- Added `opennego arena-plan` for reciprocal large-batch schedule planning and
  scorecard-vs-arena methodology boundaries.
- Added leaderboard duplicate-run protection so repeated `manifest.run_id`
  values fail fast instead of polluting aggregate rankings.

### Current Live-Run State

- Default five-model set is configured through LiteLLM/OpenRouter model IDs.
- Real provider execution requires optional LiteLLM dependencies and provider
  credentials in environment variables.
- Optional LiteLLM dependencies are installed in the local `.venv`.
- OpenRouter and OpenAI credentials are available from local Keychain under the
  OpenNegotiation service names; live commands inject them into child-process
  environment variables at execution time.
- Issue `#102` now uses a max-realism current-system OpenRouter validation
  standard: two live models, buyer/seller role swapping, 32-turn scenarios,
  8192-token LLM calls, validated real-market fixture data, all current
  `market_price_search` mode/visibility regimes, transaction guards,
  leaderboard/report generation, live user-agent sparring against every
  seller-side NPC profile, strategy evolution, strategy-candidate rerun,
  profile-by-profile comparison, marketplace validation, and external training
  adapter validation. Details are recorded in `docs/live_validation_102.md`.

### Issue And PR State

- Current backend workflow scope is tracked in GitHub issue `#29`.
- Full live workflow validation and web refresh are tracked in GitHub issue
  `#102`.
- Public hosted website work is tracked in GitHub issue `#28` and currently
  depends on resolving GitHub Pages support for the private repository.
- The earlier stacked demo PR train has been superseded by merged mainline
  slices.
- No long-lived integration PR is required for the current local demo
  state.

### Verification

- `pytest -q`: 154 passed after adding live user-strategy sparring and
  duplicate leaderboard guards.
- `compileall`: passing.
- `git diff --check`: passing.
- `opennego demo` followed by `opennego validate-demo`: passing.
- `opennego handoff`: passing with demo, market, marketplace, and role-swap
  validations.
- Product naming guard: passing; public-facing copy uses OpenNegotiation while
  legacy handles remain only in technical compatibility contexts.
- `opennego train` no-key training loop: passing and writing strategy configs.
- `opennego apply-strategy`: passing for candidate-to-config application.
- `opennego validate-marketplace`: passing for the curated registry and an
  exported shared strategy profile.
- `opennego role-swap`: passing with buyer/seller role coverage 1.0.
- `opennego arena-plan`: passing with reciprocal buyer/seller matchups and
  `opennego.arena_plan.v1`.
- Max-realism current-system live OpenRouter validation for issue `#102`:
  passing across validated market/source gates, 24 role-swapped live A2A
  benchmark runs, 24-run leaderboard/report aggregation, 36-slice baseline
  live user-agent/profile-NPC sparring, 36-slice strategy rerun, profile-by-
  profile comparisons, local marketplace validation, and external training
  adapter validation. The earlier pass also exposed and fixed a sparring
  manifest provenance gap for transaction metadata.
- Browser smoke for the static demo panel passed on narrow and wide viewports.

### Next

- Keep live provider demos small but realistic: bounded model scope is fine,
  but acceptance runs should preserve realistic turn budgets, transaction
  settings, market-source gates, tool regimes, and post-processing evidence.
- Keep expanding transaction realism through provider-neutral fixture contracts
  first; add real payment, logistics, warranty, legal/compliance, and platform
  dispute integrations only when those boundaries are decided.
- Production-verify eBay Marketplace Insights ingestion with approved
  credentials, then add hosted refresh jobs and non-eBay licensed/live source
  adapters.
- Resolve public hosted site deployment for the `web` branch or choose another
  hosting target.
