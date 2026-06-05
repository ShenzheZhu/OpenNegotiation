# MVP Readiness Audit

Date: 2026-06-05

This audit answers the current readiness question for website/demo surfaces,
architecture, and tests.

## Summary

No-key MVP development is implemented and locally verified on the current
stacked branch set. It is not fully shipped because the PR stack is still draft
and not merged to `main`. Live five-model provider execution is also not
verified in this environment because provider API keys are not present in shell
environment variables.

## Website / Demo Surfaces

Verified no-key surfaces:

- `opennego mvp-demo --output-dir /tmp/opennego-readiness-mvp --report /tmp/opennego-readiness-mvp.html`
- `opennego spar --output-dir /tmp/opennego-readiness-sparring --report /tmp/opennego-readiness-sparring.html --opponent-profile seller_hardline_anchor_v1 --opponent-profile seller_hidden_fees_v1`

Browser smoke evidence:

- MVP dashboard rendered Leaderboard Preview, Training / Prompt Optimization,
  Strategy Marketplace, Hardline Anchor Seller, and `buyer_overpaid_market`.
- Sparring report rendered OpenNego strategy sparring report,
  `fixture_profile_diagnosis`, Hardline Anchor Seller, Hidden Fees Seller, and
  `buyer_overpaid_market`.
- Both pages passed desktop 1280px and mobile 390px checks.
- No console errors were observed.
- No body-level horizontal overflow was observed.

Not complete:

- There is no hosted website in this repository.
- Live provider attempt status can render, but a fresh live five-model run was
  not executed in this environment.

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
- Strategy profiles currently drive diagnosis and curriculum metadata, not live
  profile-backed model opponents.
- Hosted marketplace backend and provider-backed coaching are not implemented.

## Tests And Static Checks

Verified commands:

```bash
pytest -q
PYTHONPYCACHEPREFIX=/tmp/opennego-pycache PYTHONPATH=src python3 -m compileall -q src tests
git diff --check
secret-pattern scan for common provider key prefixes
```

Latest local result on this readiness branch:

- `pytest -q`: 55 passed.
- `compileall`: passing.
- `git diff --check`: passing.
- Secret-pattern scan: no matches.

Live provider status:

- `OPENROUTER_API_KEY`: unset.
- `OPENAI_API_KEY`: unset.
- `ANTHROPIC_API_KEY`: unset.
- `GEMINI_API_KEY`: unset.
- `GOOGLE_API_KEY`: unset.

Therefore live provider execution is not verified in this audit.

## PR Stack Status

Current stack:

1. `#19`: real-market demo gym, draft.
2. `#21`: policy-learning MVP and NPC registry, draft, stacked on `#19`.
3. `#23`: no-key strategy sparring suite, draft, stacked on `#21`.
4. `#25`: sparring suite HTML report, draft, stacked on `#23`.
5. `#26`: MVP readiness audit and architecture handoff, stacked on `#25`.

Readiness conclusion:

- No-key local MVP: implemented and verified.
- Website/demo surfaces: implemented as static local reports and verified.
- Architecture: documented and guarded by tests.
- Tests: passing locally.
- Shipped status: not complete until the draft PR stack is reviewed, merged, and
  any desired live provider demo is run with credentials supplied safely.
