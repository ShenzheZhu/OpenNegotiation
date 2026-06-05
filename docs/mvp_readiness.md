# MVP Readiness Audit

Date: 2026-06-05

This audit answers the current readiness question for website/demo surfaces,
architecture, and tests.

## Summary

No-key MVP development is implemented and locally verified on the current
stacked branch set. A small live five-model OpenRouter run is also verified
after fixing the strict JSON-schema response format used by LLM agents. It is
not fully shipped until the stacked PRs are merged to `main`.

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

- There is no hosted website in this repository.
- The website/demo surface is currently a generated local static report, not a
  hosted public site.

## Architecture

Implemented:

- Provider-neutral core environment through `AgentPort`, `LLMPort`, `ToolPort`,
  and `TransactionPort`.
- LiteLLM isolated behind `opennego.adapters`.
- Versioned benchmark artifacts for scenario, manifest, trace, and metrics.
- Policy-learning battle reports that read benchmark artifacts.
- Local NPC strategy registry and no-key sparring suite.
- Static HTML report generators for benchmark/MVP and sparring surfaces.
- Architecture overview in `docs/architecture.md`.
- Python runtime declaration aligned to current syntax: Python 3.10+.

Guardrail:

- `tests/test_architecture_boundaries.py` checks that provider-specific imports
  do not leak into provider-neutral core modules.

Known architecture limits:

- Runner-level custom agent registration is not implemented.
- Strategy profiles are instantiated as deterministic fixture counterparties,
  not live provider-backed model opponents.
- Hosted marketplace backend and provider-backed coaching are not implemented.

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

- `pytest -q`: 57 passed.
- `compileall`: passing.
- `git diff --check`: passing.
- Secret-pattern scan: no matches.

Live provider status:

- OpenRouter credentials were supplied from local Keychain at command time.
- No API keys were written to the repository or generated live artifacts.
- Live five-model run: 5 completed, 0 failed.

Live run summary:

| Model | Status | Outcome | Deal price | LLM calls | Total tokens | Cost USD |
| --- | --- | --- | --- | --- | --- | --- |
| `openrouter/openai/gpt-5.4-pro` | completed | timeout | - | 4 | 3500 | 0.237 |
| `openrouter/anthropic/claude-opus-4.8` | completed | timeout | - | 2 | 2937 | 0.019025 |
| `openrouter/google/gemini-3.1-pro-preview` | completed | timeout | - | 4 | 3642 | 0.015924 |
| `openrouter/x-ai/grok-4.3` | completed | deal | 550.0 | 1 | 1011 | 0.0015356 |
| `openrouter/qwen/qwen3-235b-a22b` | completed | timeout | - | 4 | 7220 | 0.009732 |

## PR Stack Status

Current stack:

1. `#19`: real-market demo gym, draft.
2. `#21`: policy-learning MVP and NPC registry, draft, stacked on `#19`.
3. `#23`: no-key strategy sparring suite, draft, stacked on `#21`.
4. `#25`: sparring suite HTML report, draft, stacked on `#23`.
5. `#27`: MVP readiness audit, live-model schema fix, and architecture
   handoff, stacked on `#25`.

Readiness conclusion:

- No-key local MVP: implemented and verified.
- Website/demo surfaces: implemented as static local reports and verified.
- Architecture: documented and guarded by tests.
- Tests: passing locally.
- Live provider smoke: verified with five OpenRouter models.
- Shipped status: not complete until the draft PR stack is merged and any
  hosted/public demo target is selected.
