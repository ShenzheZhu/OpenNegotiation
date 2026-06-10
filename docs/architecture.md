# OpenNegotiation Architecture

This document describes the system layers and the boundaries that stay stable
while the benchmark grows.

## Product Layers

OpenNegotiation is organized around three product layers:

1. **Benchmark**: run agent-to-agent negotiation and transaction scenarios,
   then write versioned artifacts.
2. **Training / prompt optimization**: turn completed runs into battle reports
   with trace-grounded lessons, strategy-layer prompt patches, strategy
   candidates, and before/after comparison artifacts.
3. **Strategy marketplace**: expose curated NPC profiles and sparring suites so
   users can test their agents against repeatable opponent archetypes.

The implementation is deterministic and no-key by default. Live model runs are
optional and routed through LiteLLM.

## Runtime Flow

```text
Config / CLI
  -> runner or demo orchestrator
  -> NegotiationEnvironment
  -> AgentPort implementations
  -> ToolPort / TransactionPort implementations
  -> artifact writers
  -> metrics, battle reports, and static HTML reports
  -> optional strategy candidate reruns through sparring
```

Core run artifacts are the source of truth:

- `scenario.json`
- `manifest.json`
- `trace.jsonl`
- `metrics.json`

Training and visualization layers read these artifacts instead of inventing
parallel logs.

## Module Boundaries

| Module | Responsibility |
| --- | --- |
| `schema.py` | shared dataclasses, roles, actions, and parsing helpers |
| `environment.py` | buyer-seller loop, tool visibility, transaction invocation, transcript construction |
| `runner.py` | config-driven experiment execution and artifact emission |
| `artifacts.py` | versioned scenario, manifest, trace, metrics, and JSON I/O |
| `metrics.py` | run-level scoring functions |
| `leaderboard.py` | run aggregation, participant role coverage, role-track scorecards |
| `arena.py` | reciprocal schedule planning for larger benchmark batches |
| `role_swap.py` | buyer/seller role-swapped benchmark tracks |
| `learning.py` | battle-report generation and NPC strategy registry parsing |
| `evolution.py` | strategy candidates, patches, and before/after comparisons |
| `strategy_config.py` | applied strategy configs with fixed-base/editable-strategy layers |
| `sparring.py` / `training.py` | sparring suite orchestration and the train loop |
| `marketplace.py` | strategy profile export, registry installation, validation |
| `market_sources.py` / `market_ingestion.py` / `market_validation.py` | source policy gates, sold-comps normalization, fixture validation |
| `report.py` / `sparring_report.py` | dependency-free static HTML reports |
| `demo.py` / `model_demo.py` | one-command demo bundle and live model demo |
| `ports/` | provider-neutral contracts for agents, LLMs, tools, transactions |
| `adapters/` | concrete provider bindings (LiteLLM, eBay Marketplace Insights) |
| `tools/` / `transactions/` | fixture-backed tool and settlement implementations |
| `agents/` | scripted baselines and LLM-backed baseline agents |
| `cli/` | command modules grouped by surface, registered in `cli/__init__.py` |

## CLI Layer

`opennego.cli` is a package of focused command modules:

- `cli/benchmark.py`: `run`, `report`, `leaderboard`, `role-swap`, `arena-plan`
- `cli/demo.py`: `demo`, `validate-demo`, `run-models`
- `cli/learning.py`: `strategies`, `spar`, `learn`, `evolve`, `compare`,
  `train`, `apply-strategy`, training adapter export/validation
- `cli/market.py`: source policies, `ingest-market`, `ingest-ebay`,
  `validate-market`
- `cli/marketplace.py`: `marketplace-export`, `validate-marketplace`
- `cli/smoke.py`: the default deterministic smoke run

Commands print structured JSON to stdout and use exit code `0` for success,
`1` for completed-with-failures, and `2` for usage or validation errors.

## Provider Boundary

The environment, schema, metrics, artifacts, learning, sparring, and report
layers must remain provider-neutral. They may depend on `opennego.ports`, but
they must not import LiteLLM or provider SDKs directly.

Provider-specific behavior belongs in:

- `src/opennego/adapters/`
- optional demo runners that explicitly exercise provider-backed agents
- manifests and failure artifacts, after redaction

`tests/test_architecture_boundaries.py` guards the provider-neutral core from
importing concrete adapters.

## Prompt Boundary

OpenNegotiation separates prompt state into two layers:

- **Base**: fixed sandbox protocol, role rules, action schema, tool
  permissions, transaction constraints, and invariant checks.
- **Strategy**: user-editable tactics, concession policy, risk tolerance,
  disclosure behavior, opponent modeling, and tool-use policy.

Policy learning can suggest changes to the strategy layer. It must not mutate
the base sandbox protocol.

## Current Known Limits

- Experiment configs support built-in no-key agents and built-in LLM
  buyer/seller agents. Python API users can also register custom runner and
  sparring factories. The CLI can load explicit local factory files, but it
  does not auto-discover modules or install remote plugins.
- Strategy sparring defaults to deterministic fixture counterparties. Python
  API callers can supply profile-backed provider agents behind `LLMPort`, but
  the CLI does not load arbitrary live NPC modules.
- Local marketplace profile export and validation are supported; hosted
  marketplace, account-backed sharing, and provider-backed coaching are out of
  scope.
- Live model demos require provider credentials supplied through environment
  variables or a local secret manager. Credentials must never appear in the
  repository or generated artifacts.
