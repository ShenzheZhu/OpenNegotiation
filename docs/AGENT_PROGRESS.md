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

### Current Live-Run State

- Default five-model set is configured through LiteLLM/OpenRouter model IDs.
- Real provider execution requires optional LiteLLM dependencies and provider
  credentials in environment variables.
- Optional LiteLLM dependencies are installed in the local `.venv`.
- The current local environment did not expose provider API keys through shell
  environment variables when checked.

### Issue And PR State

- Scope is tracked in GitHub issue `#18`.
- Draft PR `#19` is open from `proto/real-market-benchmark-18` to `main`.
- Keep PR `#19` in draft until a tiny live five-model run is generated and the
  report is refreshed from real provider artifacts.

### Verification

- `pytest -q`: passing after the model-demo runner was added.
- `compileall`: passing.
- `git diff --check`: passing.
- Browser smoke for the static demo panel passed on narrow and wide viewports.

### Next

- Run the five-model demo with a small token budget and refresh the report from
  real provider artifacts.
- Review live traces for malformed JSON, invalid offers, and provider-specific
  failures before presenting results as anything beyond a demo.
