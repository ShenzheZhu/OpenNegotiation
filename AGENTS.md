# Repository Guidelines

## Project Structure

OpenNego uses a `src/` Python package layout.

- `src/opennego/schema.py`: shared dataclasses, action types, and parsing
  helpers.
- `src/opennego/environment.py`: core buyer-seller loop and private tool trace
  handling.
- `src/opennego/tools/`: tool interfaces and concrete tool implementations.
- `src/opennego/agents/`: baseline agents used for deterministic smoke tests.
- `src/opennego/metrics.py`: run-level evaluation metrics.
- `examples/data/`: small fixtures for local demos.
- `tests/`: pytest regression tests.

Generated outputs should go under `results/`, `runs/`, or `artifacts/` and
should not be committed unless they are curated examples.

## Development Commands

```bash
python -m pip install -e ".[dev]"
python -m opennego.cli --products-file examples/data/products.json --market-comps-file examples/data/market_comps.json
pytest
```

## Coding Style

Use Python 3.9+ and keep the core package provider-neutral. Prefer explicit
dataclasses, small pure functions, and deterministic tests. Do not bind the
environment layer directly to a specific LLM provider or web API.

Tool calls are part of the research surface. Preserve provenance, arguments,
results, and whether the event is private to one agent or visible to both.

## Testing

Every new environment behavior should have a focused pytest. For LLM or live
tool integrations, keep a deterministic fake or fixture-backed path so CI can
exercise the contract without external credentials.

## Secrets

Never commit API keys, cookies, live marketplace credentials, or generated raw
browser traces that may contain personal data.
