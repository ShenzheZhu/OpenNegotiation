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
  benchmark artifacts, battle report, and MVP HTML page.
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
- Added profile-backed LLM NPC factories behind `LLMPort` for Python API
  sparring.
- Added config-runner `llm_buyer` and `llm_seller` agent kinds behind
  provider-neutral `LLMPort` factories and CLI LiteLLM preflight.
- Added explicit CLI local agent factory loading for benchmark configs and
  sparring user agents.

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
  slices through PR `#48`.
- No active PR is required for the current local no-key MVP state.

### Verification

- `pytest -q`: 88 passed after CLI local agent factory loading.
- `compileall`: passing.
- `git diff --check`: passing.
- Browser smoke for the static demo panel passed on narrow and wide viewports.

### Next

- Keep live provider demos small and label them as smoke runs, not batch
  benchmark evidence.
- Expand the transaction layer beyond deterministic settlement guards into
  richer shipping, payment, return, warranty, and dispute workflows.
- Add offline/live real-market data ingestion once API, scraping, and privacy
  boundaries are decided.
- Resolve public hosted site deployment for the `web` branch or choose another
  hosting target.
