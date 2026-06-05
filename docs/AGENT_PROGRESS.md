# Agent Progress Log

This file tracks concrete engineering progress during the OpenNego bootstrap.
Do not record API keys, cookies, credentials, or raw live-provider payloads here.

## 2026-06-05

### Completed

- Bootstrapped a fixture-backed real-market demo around a used iPhone product
  cluster.
- Added market-reference schema and metrics so C2C scenarios can be scored
  against sold-comparable anchors instead of pretending seller cost is observed.
- Added a static HTML report generator with an OpenNego overview, mechanism,
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
- Added the first no-key policy-learning MVP slice: NPC strategy registry,
  `opennego strategies`, `opennego learn`, battle-report JSON, and
  trace-grounded strategy prompt patches.
- Integrated policy-learning reports and NPC strategy profiles into the static
  HTML demo report.
- Added `examples/reports/opennego_mvp_demo.html` as the curated no-key MVP
  page covering benchmark, training/prompt optimization, and strategy
  marketplace.
- Added `opennego mvp-demo` as the one-command no-key flow for generating the
  benchmark artifacts, leaderboard summary, bundle manifest, battle report, and
  MVP HTML page.
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
- Added `opennego validate-market` for no-key product, comparable, and dataset
  manifest consistency checks.
- Added `opennego leaderboard` for machine-readable run rankings, participant
  role-coverage summaries, and buyer/seller role-track scorecard aggregation.
- Added artifact-backed leaderboard rendering to `opennego report` when
  `leaderboard_summary.json` is present.
- Added `opennego.mvp_demo_bundle.v1` as a durable manifest for one-command MVP
  demo artifact handoff.
- Added `opennego validate-demo-bundle` for no-key MVP bundle release checks
  across manifest schema, artifact existence, workflow order, and artifact
  schema versions.
- Added a shared no-key workflow contract smoke for benchmark artifacts,
  leaderboard summaries, artifact-backed reports, battle reports, strategy
  candidates, sparring reruns, comparison artifacts, and local marketplace
  export.
- Added CLI LiteLLM profile NPC sparring with explicit opponent-profile
  selection and no-key fake-gateway tests.
- Added `opennego train` as a one-command no-key training loop for baseline
  sparring, strategy extraction, candidate rerun, and before/after comparison.
- Added `opennego validate-marketplace` for local strategy registry and shared
  marketplace profile release checks.
- Added `opennego role-swap` for a small no-key role-swapped benchmark track
  with combined leaderboard role coverage.

### Current Live-Run State

- Default five-model set is configured through LiteLLM/OpenRouter model IDs.
- Real provider execution requires optional LiteLLM dependencies and provider
  credentials in environment variables.
- Optional LiteLLM dependencies are installed in the local `.venv`.
- The current local environment did not expose provider API keys through shell
  environment variables when checked.

### Issue And PR State

- Current backend workflow scope is tracked in GitHub issue `#29`.
- Public hosted website work is tracked in GitHub issue `#28` and currently
  depends on resolving GitHub Pages support for the private repository.
- The earlier stacked MVP PR train has been superseded by merged mainline
  slices.
- No long-lived integration PR is required for the current local no-key MVP
  state.

### Verification

- `pytest -q`: 126 passed after adding the no-key role-swapped track.
- `compileall`: passing.
- `git diff --check`: passing.
- `opennego mvp-demo` followed by `opennego validate-demo-bundle`: passing.
- `opennego train` no-key training loop: passing.
- `opennego validate-marketplace`: passing for the curated registry and an
  exported shared strategy profile.
- `opennego role-swap`: passing with buyer/seller role coverage 1.0.
- Browser smoke for the static demo panel passed on narrow and wide viewports.

### Next

- Keep live provider demos small and label them as smoke runs, not batch
  benchmark evidence.
- Expand the transaction layer beyond deterministic lifecycle guards into real
  payment, logistics, warranty, legal/compliance, and platform dispute
  integrations when those boundaries are decided.
- Expand market-data ingestion from offline normalization toward licensed/live
  adapters only after API, scraping, and privacy boundaries are decided.
- Resolve public hosted site deployment for the `web` branch or choose another
  hosting target.
