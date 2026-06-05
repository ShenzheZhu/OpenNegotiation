# Benchmark Artifact Contract

OpenNego benchmark outputs are versioned JSON artifacts. The current schema
version is:

```text
opennego.benchmark.v1
```

Every artifact contains a `schema_version` field. Readers should reject unknown
versions instead of silently accepting incompatible data.

## Files

A run artifact directory contains:

- `scenario.json`: scenario and product contract.
- `manifest.json`: run configuration, agents, models, tool regime, output paths,
  seed, and code metadata.
- `trace.jsonl`: ordered event stream with one JSON object per line.
- `metrics.json`: run outcome and metric report.

## Scenario

`scenario.json` records the product, buyer budget, seller reservation price, max
turns, and scenario metadata. It is intended to be stable enough for external
teams to reproduce a scenario without reading Python code.

Required fields:

- `schema_version`
- `scenario_id`
- `product`
- `buyer_budget`
- `seller_reservation_price`
- `max_turns`

## Manifest

`manifest.json` records how the run was produced.

Required fields:

- `schema_version`
- `run_id`
- `scenario_id`
- `seed`
- `agents`
- `models`
- `tool_regime`
- `output_paths`
- `code_metadata`

`agents`, `models`, and `tool_regime` are intentionally dictionaries so future
runner configs can add fields without changing the core environment API.

## Trace

`trace.jsonl` is the authoritative audit trail. Each row records one event:

- public dialogue actions: `message`, `offer`, `accept`, `reject`
- private tool actions: `tool_call`
- tool result summaries and provenance
- parser, judge, and error events in future extensions

Required fields per record:

- `schema_version`
- `run_id`
- `scenario_id`
- `event_index`
- `turn`
- `role`
- `actor`
- `action_type`
- `private`

Tool events must preserve `tool_call`, `tool_result`, and `error` when
available. Private tool events are visible in the artifact for auditability, but
the environment still hides them from the counterparty during the run.

## Metrics

`metrics.json` records the outcome, deal price, completed public turns, and
metric dictionary. Metrics should be reproducible from `scenario.json` and
`trace.jsonl` when possible.

Current core metrics:

- `deal_rate`
- `tool_call_count`
- `buyer_savings_vs_list`
- `buyer_budget_slack`
- `seller_profit_vs_reservation`
- `normalized_deal_price`

## Compatibility

The artifact contract is provider-neutral. It does not assume LiteLLM, OpenAI,
OpenRouter, a live browser, or any marketplace API. Provider-specific state
belongs in adapters and manifests, not in the core environment.
