# Benchmark Artifact Contract

OpenNegotiation benchmark outputs are versioned JSON artifacts. The current schema
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

Product records may include an optional `market_reference` object for
market-grounded C2C scenarios. This records sold-comparable reference statistics
such as `reference_price`, `p25_price`, `p75_price`, `sample_size`,
`window_days`, `currency`, `source`, and `sale_mechanism`. If a market-style
fixture omits observed wholesale cost, the legacy `wholesale_price` value may be
derived from a synthetic seller reservation or market reference for
backward-compatible execution; the product attributes should record
`legacy_wholesale_basis`.

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
- system settlement actions: `transaction`
- tool result summaries and provenance
- transaction outcomes and cost/risk breakdowns
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

Transaction events use `action_type: "transaction"` and preserve a
`transaction` object with:

- `status`
- `negotiated_price`
- `buyer_total_cost`
- `seller_net_revenue`
- shipping, tax, escrow, payment, and seller fee fields
- return, reputation, and aggregate risk fields
- optional `failure_reason`
- optional metadata with computed buyer/seller settlement values and violated
  guard fields when deterministic settlement validation fails

## Metrics

`metrics.json` records the outcome, deal price, completed public turns, and
metric dictionary. Metrics should be reproducible from `scenario.json` and
`trace.jsonl` when possible.

Current core metrics:

- `deal_rate`
- `tool_call_count`
- `tool_success_count`
- `tool_failure_count`
- `private_tool_call_count`
- `public_tool_call_count`
- `tool_evidence_event_count`
- `buyer_savings_vs_list`
- `buyer_budget_slack`
- `seller_profit_vs_reservation`
- `normalized_deal_price`
- `market_reference_price`
- `market_price_gap`
- `normalized_market_gap`
- `buyer_savings_vs_market_reference`
- `seller_revenue_vs_market_reference`
- `transaction_completed_rate`
- `failed_transaction_rate`
- `buyer_total_transaction_cost`
- `seller_net_transaction_revenue`
- `transaction_risk_exposure`
- `transaction_shipping_cost`
- `transaction_tax`
- `transaction_fees`

Guard-failed transactions keep `outcome: "deal"` at the negotiation level while
recording `failed_transaction_rate: 1.0` and a transaction failure reason such as
`buyer_total_cost_exceeded` or `seller_net_revenue_below_floor`.

## Leaderboard Summary

`opennego leaderboard --input-dir <runs> --output leaderboard_summary.json`
aggregates completed run artifact directories into
`opennego.leaderboard.v1` JSON. The summary contains:

- ranked per-run rows with run id, scenario id, tool regime, score, outcome,
  deal price, buyer participant id, seller participant id, and raw metrics
- participant summaries with observed roles, role coverage, unique run count,
  role appearance count, per-role scores, average score, coverage-adjusted
  score, and balanced average score when both buyer and seller roles are present
- buyer role-track aggregates
- seller role-track aggregates

Participant ids prefer manifest model ids when available, falling back to
explicit manifest `participant_id` values and then `agent_kind:agent_name` for
scripted or custom agents. The first scorecard score uses existing
deterministic metrics: deal rate, transaction completion, normalized market
gap, and tool failure rate. Participant coverage is a contract check, not a new
negotiation metric: it makes one-role NPC/profile results visibly different
from balanced buyer/seller evaluations. Elo or Bradley-Terry fitting is a
future arena layer, not part of this deterministic summary.

## Role-Swapped Benchmark Track

`opennego role-swap --output-dir <dir> --participant-id <id>` runs a small
fixture-backed track that evaluates one strategy identity as both buyer and
seller. It writes:

- buyer-role run artifacts
- seller-role run artifacts
- `combined_runs/` with completed run artifact directories
- `leaderboard_summary.json` over the combined runs
- `role_swap_summary.json` with schema `opennego.role_swap_benchmark.v1`

The combined leaderboard should show the selected participant with buyer and
seller roles and `role_coverage: 1.0`. This is a small no-key methodology
track for external handoff, not a pairwise arena or large-batch leaderboard.

## MVP Demo Bundle

`opennego mvp-demo` writes `mvp_demo_manifest.json` with schema
`opennego.mvp_demo_bundle.v1`. The bundle manifest is a handoff index, not a
separate scoring surface. It records:

- benchmark completion and failure counts
- selected learning run id and artifact directory
- paths for `leaderboard_summary.json`, `battle_report.json`,
  `strategy_candidate.json`, and the rendered HTML report
- observed and expected schema versions for machine-readable artifacts
- ordered workflow steps used by the one-command no-key demo

`opennego validate-demo-bundle --manifest <mvp_demo_manifest.json>` validates
that handoff bundle and returns `opennego.mvp_demo_bundle_validation.v1` JSON.
It checks the bundle schema, benchmark summary fields, workflow step order,
required artifact paths, and the expected schema versions for the leaderboard
summary, battle report, and strategy candidate artifacts. A failed validation
returns a nonzero CLI exit code so release scripts can gate curated demo
bundles before handoff.

## External Handoff Package

`opennego handoff --output-dir <dir>` writes a top-level
`handoff_manifest.json` with schema `opennego.external_handoff.v1`. The handoff
manifest is the package index for external no-key model-team smoke tests. It
records:

- the package README path
- MVP demo artifact paths and benchmark completion counts
- role-swapped benchmark summary path and participant role coverage
- MVP bundle, market fixture, and strategy marketplace validation statuses
- recheck commands for the package validators
- no-key boundaries: fixture-backed data, no live marketplace collection, no
  live model-provider calls, and no hosted marketplace backend

The handoff package is ready only when the manifest `status` is `passed`.

## Compatibility

The artifact contract is provider-neutral. It does not assume LiteLLM, OpenAI,
OpenRouter, a live browser, or any marketplace API. Provider-specific state
belongs in adapters and manifests, not in the core environment.
