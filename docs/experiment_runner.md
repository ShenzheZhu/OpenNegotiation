# Experiment Runner

OpenNego supports config-driven local experiments through:

```bash
opennego run --config configs/no_key_smoke.yaml
```

The runner is intentionally in-process for now. It does not require API keys,
Docker, Postgres, or a server runtime. Each run writes the versioned benchmark
artifacts described in [benchmark_contract.md](benchmark_contract.md).

## Config Format

`configs/no_key_smoke.yaml` is the canonical no-key smoke config. It is
JSON-compatible YAML, so it can be parsed with the Python standard library.
Richer YAML syntax is accepted when `PyYAML` is installed locally, but PyYAML is
not required for the default smoke path.

Top-level fields:

- `schema_version`: must be `opennego.experiment.v1`.
- `name`: experiment name used in generated run IDs.
- `output_dir`: base directory for run outputs.
- `resume`: when true, completed run directories are skipped.
- `fail_fast`: when true, stop after the first runtime failure.
- `seeds`: list of integer seeds or `null`.
- `agents`: buyer and seller agent kinds.
- `scenarios`: product/scenario inputs.
- `tool_regimes`: tool availability matrix.
- `transaction`: optional fixture transaction simulator config.
- `metadata`: optional object copied into run manifests.

Supported agent kinds in the first runner slice:

- buyer: `tool_aware_buyer`
- seller: `scripted_seller`

Supported tool kinds in the first runner slice:

- `market_price` with `name: market_price_search`

Supported market-price tool modes:

- `clean`: use fixture prices as-is.
- `noisy`: deterministically perturb returned prices.
- `stale`: preserve prices but mark evidence with `stale_as_of` provenance.
- `adversarial`: inflate fixture prices with `adversarial_multiplier`.
- `failure`: return a structured tool failure instead of evidence.

Supported visibility shorthands:

- `buyer_private`: only the buyer can call the tool; result is private.
- `seller_private`: only the seller can call the tool; result is private.
- `symmetric_private`: both roles can call the tool; result is private.
- `shared_public` or `symmetric_public`: both roles can call the tool; result is
  visible in both transcripts.

Tool specs may also provide explicit `roles`, for example
`"roles": ["buyer", "seller"]`.

Supported transaction config in the first runner slice:

- `kind`: `fixture`.
- `enabled`: whether accepted deals should be settled.
- `shipping_cost`: fixed buyer shipping cost.
- `tax_rate`: tax applied to negotiated price.
- `escrow_fee`: fixed fee included in buyer cost and deducted from seller
  revenue.
- `payment_fee_rate`: buyer-side payment fee rate.
- `seller_fee_rate`: seller-side platform fee rate.
- `return_risk` and `reputation_risk`: deterministic risk placeholders.
- `payment_success`: when false, records a failed transaction outcome.

## Minimal Example

```json
{
  "schema_version": "opennego.experiment.v1",
  "name": "no_key_smoke",
  "output_dir": "runs/no_key_smoke",
  "resume": true,
  "fail_fast": true,
  "transaction": {
    "kind": "fixture",
    "enabled": true,
    "shipping_cost": 18.0,
    "tax_rate": 0.08,
    "escrow_fee": 4.0,
    "payment_fee_rate": 0.02,
    "seller_fee_rate": 0.05,
    "return_risk": 0.03,
    "reputation_risk": 0.02
  },
  "seeds": [7],
  "agents": {
    "buyer": {"kind": "tool_aware_buyer"},
    "seller": {"kind": "scripted_seller"}
  },
  "scenarios": [
    {
      "id": "camera_001",
      "products_file": "examples/data/products.json",
      "product_index": 0,
      "max_turns": 8
    }
  ],
  "tool_regimes": [
    {"id": "no_tools", "tools": []},
    {
      "id": "buyer_private_market_search",
      "tools": [
        {
          "name": "market_price_search",
          "kind": "market_price",
          "source": "examples/data/market_comps.json",
          "visibility": "buyer_private",
          "mode": "clean"
        }
      ]
    }
  ]
}
```

The runner executes the cross product of:

- scenarios
- tool regimes
- seeds

Generated run IDs use:

```text
<experiment-name>-<scenario-id>-<tool-regime-id>-seed-<seed>
```

## Output Layout

For the default smoke config, outputs are written under:

```text
runs/no_key_smoke/
  no_key_smoke-camera_001-no_tools-seed-7/
    manifest.json
    scenario.json
    trace.jsonl
    metrics.json
  no_key_smoke-camera_001-buyer_private_market_search-seed-7/
    manifest.json
    scenario.json
    trace.jsonl
    metrics.json
  ...
```

A run is considered complete for resume only when all four artifact files exist
and can be parsed with the benchmark contract loaders.

## Validation

The runner validates all config inputs before starting the first run. Missing
product files, unknown agent kinds, unsupported tool kinds, run ID collisions,
and malformed config fields fail without creating the output directory.

Runtime failures are reported in the JSON summary. The CLI exits with:

- `0`: all runs completed or skipped.
- `1`: at least one run failed.
- `2`: config validation failed.

## Static Demo Report

Small local artifact directories can be rendered into a static HTML discussion
panel:

```bash
opennego report --input-dir /tmp/opennego-real-market-demo --output /tmp/opennego-real-market-demo.html
```

The report is dependency-free and reads the same `manifest.json`,
`scenario.json`, `trace.jsonl`, and `metrics.json` files used by the benchmark
contract. It is meant for small demos and design reviews, not as the final public
leaderboard frontend.

## Five-Model Demo

For a small live-model run:

```bash
opennego run-models --output-dir /tmp/opennego-five-model-demo
opennego report --input-dir /tmp/opennego-five-model-demo --output /tmp/opennego-five-model-demo.html
```

`run-models` runs a fixed real-market scenario across a short default set of
five LiteLLM/OpenRouter model IDs. It keeps the seller scripted so the demo
isolates buyer-side model behavior and avoids pairwise arena cost.
