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

Supported built-in no-key agent kinds:

- buyer: `tool_aware_buyer`
- seller: `scripted_seller`

Supported built-in LLM agent kinds:

- buyer: `llm_buyer`
- seller: `llm_seller`

Python API callers may also register custom provider-neutral `AgentPort`
factories and reference those keys from the same `agents` block. Each agent spec
may include a `params` object passed to the factory:

```python
summary = run_experiment_config(
    "configs/custom_agent_eval.yaml",
    agent_factories={"my_buyer": my_buyer_factory},
)
```

```json
"agents": {
  "buyer": {
    "kind": "my_buyer",
    "params": {"name": "team_a_buyer", "max_price": 760}
  },
  "seller": {"kind": "scripted_seller"}
}
```

The CLI can also load explicit local factories:

```bash
opennego run \
  --config configs/custom_agent_eval.yaml \
  --agent-factory my_buyer=/absolute/path/to/my_agents.py:my_buyer_factory
```

`--agent-factory` may be provided multiple times. Each loaded function receives
`(role, params)` and must return a fresh `AgentPort`. The runner still validates
the returned role, name, and `act(context)` contract before creating run
outputs. Automatic module discovery, remote plugin installation, and hosted
strategy execution are out of scope for this path.

## LLM Config Agents

LLM config agents run through the same experiment runner, environment, tool
runtime, transaction simulator, and artifact contracts as no-key agents. The
core runner stays provider-neutral: Python API callers must pass an `LLMPort`
factory, while the CLI wires these kinds to `LiteLLMGateway` after dependency
and credential preflight checks.

Each LLM agent spec requires `params.model`. Optional params are `name`,
`tool_policy`, `temperature`, and `max_tokens`:

```json
"agents": {
  "buyer": {
    "kind": "llm_buyer",
    "params": {
      "model": "openrouter/openai/gpt-4o-mini",
      "name": "llm_buyer:gpt-4o-mini",
      "tool_policy": "available",
      "temperature": 0.0,
      "max_tokens": 256
    }
  },
  "seller": {
    "kind": "llm_seller",
    "params": {
      "model": "openrouter/anthropic/claude-3.5-haiku",
      "name": "llm_seller:claude-3.5-haiku",
      "tool_policy": "available"
    }
  }
}
```

For no-key tests or custom providers, inject an `LLMPort` factory:

```python
summary = run_experiment_config(
    "configs/llm_pair.example.yaml",
    llm_factory=my_llm_port_factory,
)
```

For live LiteLLM execution from the CLI:

```bash
python -m pip install -e ".[llm]"
OPENROUTER_API_KEY=... opennego run --config configs/llm_pair.example.yaml
```

Run manifests record role-to-model metadata under `models`, so downstream
reports can distinguish benchmark rows by model id.

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
- `dispute_risk`: deterministic dispute-risk placeholder.
- `payment_success`: when false, records a failed transaction outcome.
- `shipping_success`: when false, records a post-payment shipping failure.
- `item_matches_listing`: when false, records an item-mismatch dispute.
- `max_buyer_total_cost`: optional buyer all-in cost cap for settlement
  validation.
- `min_seller_net_revenue`: optional seller net revenue floor for settlement
  validation.
- `max_dispute_risk`: optional deterministic dispute-risk cap.
- `return_window_days`: return-window policy in days.
- `min_return_window_days`: optional minimum acceptable return-window policy.

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
    "reputation_risk": 0.02,
    "dispute_risk": 0.01,
    "max_buyer_total_cost": 900.0,
    "min_seller_net_revenue": 700.0,
    "max_dispute_risk": 0.08,
    "return_window_days": 14,
    "min_return_window_days": 7
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
contract. If `leaderboard_summary.json` is present, the visible leaderboard
preview and participant coverage table are rendered from that versioned summary
artifact instead of recalculating the ranking only for HTML. It is meant for
small demos and design reviews, not as the final public leaderboard frontend.

## Five-Model Demo

For a small live-model run:

```bash
opennego run-models --output-dir /tmp/opennego-five-model-demo --max-turns 4 --max-tokens 256
opennego report --input-dir /tmp/opennego-five-model-demo --output /tmp/opennego-five-model-demo.html
```

`run-models` runs a fixed real-market scenario across a short default set of
five LiteLLM/OpenRouter model IDs. It keeps the seller scripted so the demo
isolates buyer-side model behavior and avoids pairwise arena cost.

The model demo writes a top-level `summary.json` next to the per-model run
directories. Completed runs use the standard benchmark artifacts. Failed runs
write a redacted `failure.json` with model id, error type, safe error text, and
usage counters collected before failure. The static HTML report only includes
completed benchmark runs in the leaderboard because it requires `manifest.json`,
`scenario.json`, `trace.jsonl`, and `metrics.json`, but it renders a separate
attempt-status table when `summary.json` is present.

## Role-Swapped Track

For a no-key role-coverage check:

```bash
opennego role-swap --output-dir /tmp/opennego-role-swap --participant-id baseline_strategy
```

The command reuses a base fixture config, runs the selected participant id as
buyer and seller against fixed counterparties, copies completed runs into
`combined_runs/`, and writes a combined `leaderboard_summary.json`. The
`role_swap_summary.json` artifact uses schema `opennego.role_swap_benchmark.v1`
and records the participant roles and role coverage. This track is intentionally
small and deterministic; it is not an Elo or Bradley-Terry arena.
