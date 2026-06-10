# Contributing to OpenNegotiation

Thanks for your interest in improving OpenNegotiation. This guide covers the
local development workflow, code standards, and the checks every change must
pass.

## Development Setup

Use Python 3.10 or newer.

```bash
git clone https://github.com/Kordi-AI/OpenNegotiation.git
cd OpenNegotiation
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

For LLM-backed agents, install the optional gateway dependency:

```bash
python -m pip install -e ".[dev,llm]"
```

## Running Checks

Every change must pass the no-key gate locally before review:

```bash
PYTHONPATH=src python -m compileall -q src tests
pytest -q
opennego run --config configs/no_key_smoke.yaml --output-dir /tmp/opennego-smoke
```

The smoke benchmark should report `total_runs: 5`, `completed: 5`, `failed: 0`.
CI runs the same gate on every pull request.

## Project Layout

| Path | Purpose |
| --- | --- |
| `src/opennego/schema.py` | shared dataclasses, action types, parsing helpers |
| `src/opennego/environment.py` | core buyer-seller loop and private tool traces |
| `src/opennego/runner.py` | config-driven experiment runner and resume logic |
| `src/opennego/ports/` | provider-neutral contracts (agents, LLMs, tools, transactions) |
| `src/opennego/adapters/` | concrete provider integrations (LiteLLM, eBay) |
| `src/opennego/agents/` | scripted and LLM-backed baseline agents |
| `src/opennego/tools/` | tool interfaces and implementations |
| `src/opennego/transactions/` | deterministic transaction simulators |
| `src/opennego/cli/` | command modules grouped by surface |
| `configs/` | experiment configs, including no-key smoke runs |
| `examples/data/` | small fixtures for local demos |
| `tests/` | deterministic regression tests |

Generated outputs belong under `results/`, `runs/`, or `artifacts/` (all
gitignored). Do not commit generated artifacts unless they are curated
examples under `examples/`.

## Design Rules

These boundaries keep the core reusable and are enforced by
`tests/test_architecture_boundaries.py`:

1. **Ports before adapters.** Core code may depend on `opennego.ports`;
   provider SDKs such as LiteLLM are imported lazily and only from
   `opennego.adapters`. The environment layer never binds directly to a
   specific LLM provider or web API.
2. **Tool calls are part of the research surface.** Preserve provenance,
   arguments, results, and whether each event is private to one agent or
   visible to both.
3. **Artifacts are the source of truth.** Reports and learning layers read
   the versioned run artifacts (`scenario.json`, `manifest.json`,
   `trace.jsonl`, `metrics.json`) instead of inventing parallel logs.
4. **Determinism by default.** Every new environment behavior needs a focused
   pytest. Live LLM and live API integrations must keep a deterministic fake
   or fixture-backed path so CI can exercise the contract without
   credentials.

## Code Style

- Python 3.10+, explicit dataclasses, small pure functions.
- Prefer provider-neutral naming in core modules.
- Match the existing comment density: code should explain itself; comments
  state constraints the code cannot show.

## Secrets

Never commit API keys, cookies, live marketplace credentials, or raw browser
traces that may contain personal data. Live commands read credentials from
environment variables only.

## Pull Requests

- Keep PRs focused on one change.
- Include or update tests for any behavior change.
- Update documentation when you change a CLI command, config field, or
  artifact schema.
- Artifact schema changes require a version bump (`opennego.<name>.v<N>`) and
  a note in `CHANGELOG.md`.

## Releases

Maintainers cut releases from `main` after the no-key gate passes:

1. Update the version in `pyproject.toml` and move `CHANGELOG.md` entries from
   *Unreleased* to the new version.
2. Run the full check suite above, plus `opennego demo` followed by
   `opennego validate-demo --manifest <output>/demo_manifest.json`.
3. Tag the release (`vX.Y.Z`) and publish notes from the changelog.
