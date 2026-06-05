# Release Checklist

Use this checklist before handing OpenNego to an external model team.

## Local No-Key Gate

Use Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
PYTHONPATH=src python -m compileall -q src tests
pytest -q
opennego run --config configs/no_key_smoke.yaml --output-dir /tmp/opennego-release-smoke
```

Expected smoke summary:

- `total_runs`: 5
- `completed`: 5
- `failed`: 0

## Artifact Spot Check

Inspect:

```text
/tmp/opennego-release-smoke/no_key_smoke-camera_001-buyer_private_market_search-seed-7/
  manifest.json
  scenario.json
  trace.jsonl
  metrics.json
```

Confirm:

- trace contains a private `tool_call` event;
- trace contains a public `transaction` event;
- metrics include `deal_price`, `buyer_total_transaction_cost`, and
  `seller_net_transaction_revenue`;
- no credentials or local private paths are present in committed artifacts.

## External Handoff Package

For a shareable no-key package, run:

```bash
opennego handoff --output-dir /tmp/opennego-handoff
```

The command writes:

- `/tmp/opennego-handoff/README.md`
- `/tmp/opennego-handoff/handoff_manifest.json`
- MVP demo artifacts and an HTML report
- MVP bundle, market fixture, and strategy marketplace validation JSON
- role-swapped benchmark artifacts with participant role coverage

The top-level manifest uses schema `opennego.external_handoff.v1`. Treat the
package as ready only when `status` is `passed`.

## External Handoff Notes

- Start external users with `README.md`, `docs/benchmark_spec.md`, and
  `docs/agent_integration.md`.
- Make clear that `configs/no_key_smoke.yaml` is fixture-backed, not live market
  evidence.
- Ask live-model users to keep provider keys in environment variables,
  Keychain, another local secret manager, or a LiteLLM proxy config.
- Do not accept benchmark result submissions without `manifest.json`,
  `trace.jsonl`, and `metrics.json`.
