# Repository Guidelines

## Project Structure

OpenNego uses a `src/` Python package layout.

- `src/opennego/schema.py`: shared dataclasses, action types, and parsing
  helpers.
- `src/opennego/environment.py`: core buyer-seller loop and private tool trace
  handling.
- `src/opennego/artifacts.py`: versioned scenario, manifest, trace, and metrics
  artifact contracts.
- `src/opennego/runner.py`: config-driven experiment runner and resume logic.
- `src/opennego/ports/`: provider-neutral contracts for agents, LLM gateways,
  tools, and future transaction systems.
- `src/opennego/adapters/`: concrete provider integrations. LiteLLM belongs
  here, not in core environment code.
- `src/opennego/tools/`: tool interfaces and concrete tool implementations.
- `src/opennego/agents/`: baseline agents used for deterministic smoke tests.
- `src/opennego/metrics.py`: run-level evaluation metrics.
- `examples/data/`: small fixtures for local demos.
- `configs/`: local experiment configs, including no-key smoke runs.
- `docs/experiment_runner.md`: config runner schema and output layout.
- `tests/`: pytest regression tests.

Generated outputs should go under `results/`, `runs/`, or `artifacts/` and
should not be committed unless they are curated examples.

## Development Commands

```bash
python -m pip install -e ".[dev]"
python -m opennego.cli --products-file examples/data/products.json --market-comps-file examples/data/market_comps.json
opennego run --config configs/no_key_smoke.yaml
pytest
```

For LLM-backed agents, install the optional gateway dependency:

```bash
python -m pip install -e ".[dev,llm]"
```

## Coding Style

Use Python 3.9+ and keep the core package provider-neutral. Prefer explicit
dataclasses, small pure functions, and deterministic tests. Do not bind the
environment layer directly to a specific LLM provider or web API.

Use ports before adapters. Core code may depend on `opennego.ports`; provider
SDKs such as LiteLLM should only be imported lazily from `opennego.adapters`.

Tool calls are part of the research surface. Preserve provenance, arguments,
results, and whether the event is private to one agent or visible to both.

## Testing

Every new environment behavior should have a focused pytest. For LLM or live
tool integrations, keep a deterministic fake or fixture-backed path so CI can
exercise the contract without external credentials.

## Secrets

Never commit API keys, cookies, live marketplace credentials, or generated raw
browser traces that may contain personal data.
