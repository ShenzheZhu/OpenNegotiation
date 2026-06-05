# MVP Readiness Audit

Date: 2026-06-05

This audit answers the current readiness question for local demo surfaces,
architecture, CLI integration, and tests on `main`.

## Summary

The no-key local MVP and the main user-centric workflow slices are implemented
on `main`: benchmark runs, policy-learning battle reports, strategy candidate
reruns, local marketplace export, strategy sparring, transaction settlement
guards, config-level LLM agents, provider-neutral profile LLM NPCs, and CLI
loading for local user-agent factories, plus offline sold-comps ingestion.
Offline ingested datasets can optionally write an aggregate dataset manifest
with input fingerprint and quality summaries, then validate those fixtures with
`opennego validate-market`.
The no-key test suite also includes a shared workflow contract smoke for the
benchmark -> policy learning -> strategy candidate -> sparring rerun ->
comparison -> marketplace export loop.

A small live five-model OpenRouter smoke was verified earlier on 2026-06-05.
It was not rerun for this docs refresh; live provider execution remains an
optional demo path that requires local credentials.

## Website / Demo Surfaces

Verified no-key surfaces:

- `opennego mvp-demo --output-dir /tmp/opennego-readiness-mvp --report /tmp/opennego-readiness-mvp.html`
- `opennego spar --output-dir /tmp/opennego-readiness-sparring --report /tmp/opennego-readiness-sparring.html --opponent-profile seller_hardline_anchor_v1 --opponent-profile seller_hidden_fees_v1`

Browser smoke evidence:

- MVP dashboard rendered Leaderboard Preview, Training / Prompt Optimization,
  Strategy Marketplace, Hardline Anchor Seller, and `buyer_overpaid_market`.
- Sparring report rendered OpenNego strategy sparring report,
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
- Local strategy marketplace profile export and registry installation.
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
- Market fixture validation CLI for products/comps plus optional dataset
  manifest consistency checks.
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
- Transaction simulation validates deterministic settlement fees and lifecycle
  guard failures, but real payment, logistics, warranty, legal/compliance, and
  platform dispute integrations are not implemented.

## Tests And Static Checks

Verified commands:

```bash
pytest -q
PYTHONPYCACHEPREFIX=/tmp/opennego-pycache PYTHONPATH=src python3 -m compileall -q src tests
git diff --check
opennego run-models --output-dir /tmp/opennego-live-five-fixed-20260605 --max-turns 3 --max-tokens 220
secret-pattern scan for common provider key prefixes
```

Latest local result on this readiness branch:

- `pytest -q`: 106 passed.
- `compileall`: passing.
- `git diff --check`: passing.
- Secret-pattern scan: no matches.

Historical live provider status:

- OpenRouter credentials were supplied from local Keychain at command time.
- No API keys were written to the repository or generated live artifacts.
- Live five-model run earlier on 2026-06-05: 5 completed, 0 failed.

Live run summary:

| Model | Status | Outcome | Deal price | LLM calls | Total tokens | Cost USD |
| --- | --- | --- | --- | --- | --- | --- |
| `openrouter/openai/gpt-5.4-pro` | completed | timeout | - | 4 | 3500 | 0.237 |
| `openrouter/anthropic/claude-opus-4.8` | completed | timeout | - | 2 | 2937 | 0.019025 |
| `openrouter/google/gemini-3.1-pro-preview` | completed | timeout | - | 4 | 3642 | 0.015924 |
| `openrouter/x-ai/grok-4.3` | completed | deal | 550.0 | 1 | 1011 | 0.0015356 |
| `openrouter/qwen/qwen3-235b-a22b` | completed | timeout | - | 4 | 7220 | 0.009732 |

## Issue And PR Status

Current state:

- Current `main` includes the backend workflow slices through PR `#54`.
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
- Live provider smoke: historically verified with five OpenRouter models, not
  rerun in this docs refresh.
- Hosted/public site: not complete until the GitHub Pages/private-repo blocker
  is resolved or another hosting target is selected.
