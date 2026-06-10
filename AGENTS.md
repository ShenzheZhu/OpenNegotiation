# Repository Guidelines

Read [CONTRIBUTING.md](CONTRIBUTING.md) first: it defines the project layout,
design rules, check suite, and PR expectations. The notes below are the
short operational summary.

## Development Commands

```bash
python -m pip install -e ".[dev]"          # add ,llm for LiteLLM-backed agents
pytest -q
opennego run --config configs/no_key_smoke.yaml
opennego help                              # list every CLI command
```

## Hard Rules

- Keep the core package provider-neutral: core code may depend on
  `opennego.ports`; provider SDKs (LiteLLM, eBay) are imported lazily and only
  from `opennego.adapters`. `tests/test_architecture_boundaries.py` enforces
  this.
- Every new environment behavior needs a focused, deterministic pytest. Live
  integrations must keep a fixture-backed path that runs without credentials.
- Preserve tool-call provenance: arguments, results, and private/public
  visibility are part of the research surface.
- Generated outputs go under `results/`, `runs/`, or `artifacts/` (gitignored).
  Never commit credentials, raw provider payloads, or personal data.
- Artifact schema changes require a `opennego.<name>.v<N>` version bump and a
  `CHANGELOG.md` entry.
