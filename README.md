# OpenNego

OpenNego is an evaluation gym for agent-level agent-to-agent negotiation and
transaction research.

This repository is a follow-up to
[A2A-NT](https://github.com/ShenzheZhu/A2A-NT). A2A-NT studies automated
negotiation where the buyer and seller mostly rely on model-internal knowledge
and prompted constraints. OpenNego shifts the setting toward current agentic
systems: agents can call tools, gather market evidence, reduce information
asymmetry, and then negotiate or transact.

The intended scope is broader than a single consumer-negotiation benchmark:
OpenNego treats negotiation as one phase in a market lifecycle that can include
search, private tools, messaging, structured offers, payment, fulfillment, and
post-transaction validation.

## Why This Exists

Real buyer and seller agents should not negotiate only from static prompts. A
capable agent can search recent comparable sales, inspect product listings,
check reputation, estimate shipping and payment risk, and use those signals
before making an offer. OpenNego is intended to make that behavior measurable.

The first scaffold focuses on:

- tool-aware negotiation traces
- market-comparable lookup as a minimal tool
- ports-and-adapters boundaries for models, tools, and transaction systems
- explicit buyer budget and seller reservation constraints
- reproducible scripted agents for smoke tests
- metrics that separate deal outcome, price efficiency, and tool use

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m opennego.cli --products-file examples/data/products.json --market-comps-file examples/data/market_comps.json
pytest
```

Install the optional LiteLLM adapter when running LLM-backed agents:

```bash
python -m pip install -e ".[dev,llm]"
```

Example output:

```json
{
  "outcome": "deal",
  "deal_price": 760.0,
  "metrics": {
    "deal_rate": 1.0,
    "tool_call_count": 1.0
  }
}
```

## Core Abstractions

- `Scenario`: product, buyer budget, seller reservation price, and run limits.
- `AgentAction`: one step in the agent loop. Actions can be `tool_call`,
  `offer`, `accept`, `reject`, or `message`.
- `NegotiationEnvironment`: runs the buyer and seller loop, keeps private tool
  traces private from the counterparty, and records a full audit trail.
- `LLMPort`: the provider-neutral model interface used by LLM-backed agents.
- `ToolPort`: any callable information or transaction interface exposed to
  agents.
- `LiteLLMGateway`: optional adapter that routes `LLMPort` calls through
  LiteLLM-supported providers.
- `Metrics`: deal rate, buyer savings, seller profit, normalized deal price,
  and tool-call counts.
- `Benchmark artifacts`: versioned scenario, manifest, trace JSONL, and metric
  report files for reproducible external evaluation.

## Project Layout

```text
src/opennego/
  agents/        scripted baseline agents
  adapters/      concrete provider bindings such as LiteLLM
  artifacts.py   versioned benchmark artifact contracts and JSON I/O
  ports/         provider-neutral LLM, agent, and tool contracts
  tools/         tool interfaces and built-in market-price search
  cli.py         runnable smoke demo
  environment.py core negotiation loop
  metrics.py     run-level metrics
  schema.py      shared dataclasses and parsing helpers
examples/data/   tiny sample products and market comparables
tests/           regression tests for the first scaffold
docs/            research agenda and design notes
```

## Research Direction

OpenNego should support a ladder of increasingly realistic agentic settings:

1. No-tool baseline with a clean OpenNego prompt/action contract.
2. Retrieval-only agents that can inspect market comparables.
3. Web/search agents that can gather live evidence with provenance.
4. Transaction agents that can invoke checkout, escrow, logistics, or payment
   simulators.
5. Adversarial or strategic agents that can selectively disclose, bluff, or
   misuse tools.

See [docs/research_agenda.md](docs/research_agenda.md) for the initial roadmap
and [docs/benchmark_contract.md](docs/benchmark_contract.md) for the current
artifact contract. See
[docs/magentic_marketplace_architecture_notes.md](docs/magentic_marketplace_architecture_notes.md)
for architecture lessons from recent agentic marketplace work and how those
lessons translate into OpenNego-specific design choices.

## Status

This is an initial scaffold. The code is intentionally provider-neutral and uses
scripted agents so the environment and metrics can be tested without API keys.
LLM adapters, real search tools, richer product datasets, and transaction
simulators should be added behind the same interfaces.

LiteLLM is the preferred LLM gateway for real model sweeps. Keep the eval core
provider-neutral: model providers belong in adapters, not in the environment or
metrics code.

## License

TBD.
