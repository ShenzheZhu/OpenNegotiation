# OpenNego Architecture

This document summarizes the current MVP architecture and the boundaries that
should stay stable while the benchmark grows.

## Product Layers

OpenNego is organized around three product layers:

1. Benchmark: run agent-to-agent negotiation and transaction scenarios, then
   write versioned artifacts.
2. Training / prompt optimization: turn completed runs into battle reports with
   trace-grounded lessons, strategy-layer prompt patches, strategy candidates,
   and before/after comparison artifacts.
3. Strategy marketplace: expose curated NPC profiles and sparring suites so
   users can test their agents against repeatable opponent archetypes.

The current implementation is deterministic and no-key by default. Live model
runs are optional and routed through LiteLLM.

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

- `schema.py`: shared dataclasses, roles, actions, and parsing helpers.
- `environment.py`: buyer-seller loop, tool visibility, transaction invocation,
  and transcript construction.
- `runner.py`: config-driven experiment execution and artifact emission.
- `artifacts.py`: versioned scenario, manifest, trace, metrics, and JSON I/O.
- `metrics.py`: run-level scoring functions.
- `learning.py`: battle-report generation and NPC strategy registry parsing.
- `evolution.py`: strategy candidate loading, strategy patch artifacts, and
  before/after comparison artifacts.
- `sparring.py`: no-key strategy sparring suite orchestration, including
  optional application of versioned user strategy candidates.
- `report.py` and `sparring_report.py`: dependency-free static HTML reports.
- `ports/`: provider-neutral contracts for agents, LLMs, tools, and
  transactions.
- `adapters/`: concrete provider bindings such as LiteLLM.
- `tools/` and `transactions/`: fixture-backed local implementations.
- `agents/`: scripted baselines and LLM-backed baseline agents.

## Provider Boundary

The environment, schema, metrics, artifacts, learning, sparring, and report
layers must remain provider-neutral. They may depend on `opennego.ports`, but
they should not import LiteLLM or provider SDKs directly.

Provider-specific behavior belongs in:

- `src/opennego/adapters/`
- optional demo runners that explicitly exercise provider-backed agents
- manifests and failure artifacts, after redaction

The focused architecture test in `tests/test_architecture_boundaries.py` guards
the provider-neutral core from importing concrete adapters.

## Prompt Boundary

OpenNego separates prompt state into two layers:

- Base: fixed sandbox protocol, role rules, action schema, tool permissions,
  transaction constraints, and invariant checks.
- Strategy: user-editable tactics, concession policy, risk tolerance,
  disclosure behavior, opponent modeling, and tool-use policy.

Policy learning can suggest changes to the strategy layer. It must not mutate
the base sandbox protocol.

## Current Known Limits

- Python API users can register custom runner agent factories, but the CLI does
  not load arbitrary Python modules.
- Strategy sparring instantiates selected profiles as deterministic fixture
  counterparties, not live provider-backed model opponents.
- Hosted marketplace, live marketplace collection, and provider-backed coaching
  are out of scope for the no-key MVP.
- Live five-model demos require provider credentials supplied through
  environment variables, Keychain, or another local secret manager. Credentials
  must not be committed to the repository or generated artifacts.
