# OpenNegotiation

OpenNegotiation is an evaluation gym for agent-level agent-to-agent negotiation and
transaction research.

This repository is a follow-up to
[A2A-NT](https://github.com/ShenzheZhu/A2A-NT). A2A-NT studies automated
negotiation where the buyer and seller mostly rely on model-internal knowledge
and prompted constraints. OpenNegotiation shifts the setting toward current agentic
systems: agents can call tools, gather market evidence, reduce information
asymmetry, and then negotiate or transact.

The intended scope is broader than a single consumer-negotiation benchmark:
OpenNegotiation treats negotiation as one phase in a market lifecycle that can include
search, private tools, messaging, structured offers, payment, fulfillment, and
post-transaction validation.

## Why This Exists

Real buyer and seller agents should not negotiate only from static prompts. A
capable agent can search recent comparable sales, inspect product listings,
check reputation, estimate shipping and payment risk, and use those signals
before making an offer. OpenNegotiation is intended to make that behavior measurable.

The first scaffold focuses on:

- tool-aware negotiation traces
- market-comparable lookup as a minimal tool
- ports-and-adapters boundaries for models, tools, and transaction systems
- explicit buyer budget and seller reservation constraints
- reproducible scripted agents for smoke tests
- metrics that separate deal outcome, price efficiency, and tool use

## Quickstart

OpenNegotiation currently requires Python 3.10 or newer.

```bash
git clone https://github.com/Kordi-AI/OpenNego.git
cd OpenNego
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
opennego run --config configs/no_key_smoke.yaml
pytest
```

The no-key smoke benchmark is fully fixture-backed. It does not call live market
search, browser tools, payment systems, logistics APIs, or model providers.

For a small visual demo panel:

```bash
opennego run --config configs/real_market_demo.yaml --output-dir /tmp/opennego-real-market-demo
opennego report --input-dir /tmp/opennego-real-market-demo --output /tmp/opennego-real-market-demo.html
```

The generated HTML report introduces OpenNegotiation, shows the agentic negotiation
mechanism, previews a scorecard-style leaderboard, and replays the trace for the
highest-scoring fixture run.

For a machine-readable leaderboard summary:

```bash
opennego leaderboard \
  --input-dir /tmp/opennego-real-market-demo \
  --output /tmp/opennego-leaderboard.json
```

The leaderboard artifact includes ranked run rows, participant role-coverage
summaries, and buyer/seller role-track aggregates, using model ids when they
are recorded in run manifests.

For a small no-key role-swapped benchmark track:

```bash
opennego role-swap \
  --output-dir /tmp/opennego-role-swap \
  --participant-id baseline_strategy
```

This evaluates one strategy identity as both buyer and seller against fixed
fixture counterparties, then writes `role_swap_summary.json` and a combined
`leaderboard_summary.json` where role coverage can be checked directly.

For a reciprocal arena schedule plan without running a large batch:

```bash
opennego arena-plan \
  --participant model_a \
  --participant model_b \
  --participant model_c \
  --scenario-id real_market_demo \
  --seed 13 \
  --output /tmp/opennego-arena-plan.json
```

The plan uses schema `opennego.arena_plan.v1`. It records reciprocal
buyer/seller matchups, required participant role coverage, and the methodology
boundary: deterministic scorecards are the current primary summary, while
Elo/Bradley-Terry fitting is an optional future layer only after reciprocal pair
coverage exists.

For a tiny live-model demo, install the optional LiteLLM dependency and keep
provider credentials in environment variables:

```bash
python -m pip install -e ".[dev,llm]"
export OPENROUTER_API_KEY=...
opennego run-models --output-dir /tmp/opennego-five-model-demo --max-turns 4 --max-tokens 256
opennego report --input-dir /tmp/opennego-five-model-demo --output /tmp/opennego-five-model-demo.html
```

The default `run-models` set runs five buyer-side models against the same
scripted seller on the real-market fixture. It is intended for demos and smoke
checks, not as a full benchmark sweep. The command writes a top-level
`summary.json`; if a provider call fails, the failed model directory gets a
redacted `failure.json` instead of silently disappearing from the run record.

For the full no-key MVP panel covering benchmark, training / prompt
optimization, and the local strategy marketplace:

```bash
opennego mvp-demo --output-dir /tmp/opennego-mvp-demo --report /tmp/opennego-mvp-demo.html
opennego validate-demo-bundle --manifest /tmp/opennego-mvp-demo/mvp_demo_manifest.json
```

This runs the real-market fixture benchmark, writes a machine-readable
`leaderboard_summary.json` plus `mvp_demo_manifest.json`, generates a
trace-grounded battle report for a buyer agent against a curated seller NPC, and
renders a static HTML report. The battle report produces strategy-layer lessons
and prompt optimization suggestions while keeping OpenNegotiation's base sandbox
protocol fixed. The validation command returns
`opennego.mvp_demo_bundle_validation.v1` JSON and fails nonzero when required
artifacts are missing or their schema versions drift.
A curated no-key MVP page is available at
`examples/reports/opennego_mvp_demo.html`.

For an external no-key handoff package:

```bash
opennego handoff --output-dir /tmp/opennego-handoff
```

This writes `handoff_manifest.json`, a package `README.md`, MVP demo artifacts,
validation JSON, and a small role-swapped benchmark track. The manifest uses
schema `opennego.external_handoff.v1` and records whether the no-key handoff
passed its bundle, market fixture, marketplace, and role-coverage checks.

You can also inspect the local NPC strategy marketplace directly:

```bash
opennego strategies --role seller
```

To run the next no-key training loop against one or more marketplace NPC
profiles:

```bash
opennego spar \
  --output-dir /tmp/opennego-sparring \
  --report /tmp/opennego-sparring.html \
  --opponent-profile seller_hardline_anchor_v1 \
  --opponent-profile seller_hidden_fees_v1
```

This writes `/tmp/opennego-sparring/sparring_suite.json` plus one
`battle_report.json` per selected profile, then renders a compact HTML report
when `--report` is provided. By default, deterministic local agents spar
against counterparties instantiated from marketplace NPC profiles, so the
selected profile appears in the trace, manifest, opponent archetype, expected
traps, failure modes, and strategy patch.

For a one-command no-key training loop:

```bash
opennego train \
  --output-dir /tmp/opennego-training \
  --opponent-profile seller_hardline_anchor_v1 \
  --parent-strategy-id buyer_baseline
```

This writes baseline sparring artifacts, selects the lowest-scoring completed
battle report, emits `strategy_candidate.json`, applies it into a versioned
`strategy_config.json`, reruns the same NPC with that candidate, writes
`strategy_comparison.json`, and records the full handoff in
`training_loop.json`.

To apply a candidate into a reusable strategy config without running the full
training loop:

```bash
opennego apply-strategy \
  --candidate /tmp/opennego-training/strategy_candidate.json \
  --output /tmp/opennego-training/strategy_config.json \
  --strategy-id buyer_baseline_v1
```

The config uses schema `opennego.strategy_config.v1`, keeps the base sandbox
prompt fixed, stores the editable strategy prompt, and preserves candidate
lineage for external user-agent integration.

To package that strategy config for an external user agent without mutating the
agent source tree:

```bash
opennego export-training-adapter \
  --strategy-config /tmp/opennego-training/strategy_config.json \
  --output /tmp/opennego-training/external_training_adapter.json \
  --agent-kind team_buyer_agent
opennego validate-training-adapter \
  --adapter /tmp/opennego-training/external_training_adapter.json
```

The adapter package uses schema `opennego.external_training_adapter.v1` and
records the fixed base prompt, editable strategy prompt, lineage, target role,
and integration contract for the external agent.

To use a provider-backed profile NPC through LiteLLM, install the optional LLM
dependency, keep credentials in environment variables, and select explicit
opponent profiles to bound live calls:

```bash
python -m pip install -e ".[dev,llm]"
export OPENROUTER_API_KEY=...
opennego spar \
  --output-dir /tmp/opennego-live-npc-sparring \
  --opponent-profile seller_hardline_anchor_v1 \
  --opponent-llm-model openrouter/openai/gpt-4o-mini \
  --opponent-llm-max-tokens 256
```

To rerun sparring with a generated strategy candidate:

```bash
opennego spar \
  --output-dir /tmp/opennego-rerun \
  --opponent-profile seller_hardline_anchor_v1 \
  --user-strategy /tmp/opennego-mvp-demo/strategy_candidate.json
```

To share a generated strategy candidate into a local marketplace registry:

```bash
opennego marketplace-export \
  --candidate /tmp/opennego-mvp-demo/strategy_candidate.json \
  --output /tmp/opennego-mvp-demo/marketplace_profile.json \
  --profile-id shared_buyer_guard_v1 \
  --install-registry /tmp/opennego-local-marketplace.json
opennego validate-marketplace \
  --registry /tmp/opennego-local-marketplace.json \
  --profile /tmp/opennego-mvp-demo/marketplace_profile.json
```

Install the optional LiteLLM adapter when running custom LLM-backed agents:

```bash
python -m pip install -e ".[dev,llm]"
```

Example output:

```json
{
  "name": "no_key_smoke",
  "total_runs": 5,
  "completed": 5,
  "failed": 0
}
```

See [examples/outputs/no_key_smoke_summary.json][sample-summary]
and
[examples/outputs/buyer_private_market_search_metrics.json][sample-metrics]
for curated sample artifacts.

## Core Abstractions

- `Scenario`: product, buyer budget, seller reservation price, and run limits.
- `MarketReference`: optional sold-comparable reference statistics for
  market-grounded scenarios.
- `AgentAction`: one step in the agent loop. Actions can be `tool_call`,
  `offer`, `accept`, `reject`, `message`, or `transaction`.
- `NegotiationEnvironment`: runs the buyer and seller loop, keeps private tool
  traces private from the counterparty, and records a full audit trail.
- `LLMPort`: the provider-neutral model interface used by LLM-backed agents.
- `ToolPort`: any callable information or transaction interface exposed to
  agents.
- `LiteLLMGateway`: optional adapter that routes `LLMPort` calls through
  LiteLLM-supported providers.
- `Metrics`: deal rate, buyer savings, seller profit, normalized deal price,
  market-reference gap, tool-call counts, transaction cost, seller net revenue,
  and risk exposure.
- `Benchmark artifacts`: versioned scenario, manifest, trace JSONL, and metric
  report files for reproducible external evaluation.
- `Policy learning`: no-key battle reports that extract trace-grounded strategy
  lessons and prompt optimization patches from completed benchmark artifacts.
- `Strategy marketplace`: curated NPC profiles with fixed base protocol prompts
  and editable strategy prompts for sparring and curriculum design.
- `Marketplace validation`: no-key checks for profile schema versions, fixed
  base-prompt metadata, editable strategy-layer metadata, and local registry
  consistency.

## Project Layout

```text
src/opennego/
  agents/        scripted and LLM-backed baseline agents
  adapters/      concrete provider bindings such as LiteLLM
  artifacts.py   versioned benchmark artifact contracts and JSON I/O
  ports/         provider-neutral LLM, agent, and tool contracts
  transactions/  deterministic transaction simulators
  tools/         tool interfaces and built-in market-price search
  cli.py         runnable smoke demo
  environment.py core negotiation loop
  metrics.py     run-level metrics
  schema.py      shared dataclasses and parsing helpers
examples/data/   tiny sample products and market comparables
examples/outputs curated no-key sample outputs
tests/           regression tests and no-key benchmark contracts
docs/            research agenda and design notes
```

## Research Direction

OpenNegotiation should support a ladder of increasingly realistic agentic settings:

1. No-tool baseline with a clean OpenNegotiation prompt/action contract.
2. Retrieval-only agents that can inspect market comparables.
3. Web/search agents that can gather live evidence with provenance.
4. Transaction agents that can invoke checkout, escrow, logistics, or payment
   simulators.
5. Adversarial or strategic agents that can selectively disclose, bluff, or
   misuse tools.

See [docs/research_agenda.md](docs/research_agenda.md) for the initial roadmap
and [docs/benchmark_contract.md](docs/benchmark_contract.md) for the current
artifact contract. See [docs/benchmark_spec.md](docs/benchmark_spec.md) for the
benchmark structure and [docs/agent_integration.md](docs/agent_integration.md)
for external agent integration. See
[docs/magentic_marketplace_architecture_notes.md](docs/magentic_marketplace_architecture_notes.md)
for architecture lessons from recent agentic marketplace work and how those
lessons translate into OpenNegotiation-specific design choices. See
[docs/experiment_runner.md](docs/experiment_runner.md) for config-driven
benchmark execution and [docs/llm_baselines.md](docs/llm_baselines.md) for the
structured action contract used by LLM-backed agents. See
[docs/transaction_simulator.md](docs/transaction_simulator.md) for the first
fixture-backed settlement model and [docs/troubleshooting.md](docs/troubleshooting.md)
for common setup and parser issues. See
[docs/release_checklist.md](docs/release_checklist.md) for the no-key handoff
gate and [docs/naming.md](docs/naming.md) for the OpenNegotiation vs `opennego`
technical-handle policy. See
[docs/real_market_benchmark_design.md](docs/real_market_benchmark_design.md) for
the market-grounded dataset and leaderboard design. See
[docs/policy_learning.md](docs/policy_learning.md) for the prompt-optimization
training loop and NPC strategy marketplace MVP. See
[docs/architecture.md](docs/architecture.md) for the current module boundaries
and [docs/mvp_readiness.md](docs/mvp_readiness.md) for the website,
architecture, and test readiness audit.

## Status

This is a provider-neutral MVP scaffold with no-key benchmark, training,
leaderboard, marketplace-export, and transaction-simulation paths. Scripted
agents and fixtures keep the core environment testable without API keys, while
LLM adapters and real-search style tools live behind explicit ports.

LiteLLM is the preferred LLM gateway for real model sweeps. Keep the eval core
provider-neutral: model providers belong in adapters, not in the environment or
metrics code.

## License

TBD.

[sample-summary]: examples/outputs/no_key_smoke_summary.json
[sample-metrics]: examples/outputs/buyer_private_market_search_metrics.json
