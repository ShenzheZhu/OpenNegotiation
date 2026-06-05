# Benchmark Spec

OpenNego evaluates agent-to-agent negotiation as part of a broader transaction
workflow. The benchmark is intentionally provider-neutral: model access, tools,
and transaction systems are attached through ports.

## Run Unit

A run is one scenario x tool regime x seed x agent pair. The config runner
builds the Cartesian product declared in an experiment config and writes one
artifact directory per run.

## Scenario

The first scenario schema is product-centric:

- product id, name, description, condition
- list price and wholesale price
- buyer budget
- seller reservation price
- max public turns
- optional metadata

A2A-NT-style product records can be loaded, but product resale is one domain,
not the whole framework.

## Agents

Agents implement `AgentPort`:

```python
class AgentPort(Protocol):
    name: str
    role: Role

    def act(self, context: AgentContext) -> AgentAction:
        ...
```

Current built-in baselines:

- `ToolAwareBuyer`
- `ScriptedSeller`
- `LLMNegotiationAgent`

LLM agents use `LLMPort` and a structured JSON action contract. They do not
import provider SDKs directly.

## Tools And Regimes

Tools implement `ToolPort`. A tool regime controls:

- which roles can see a tool in `AgentContext.available_tools`
- whether tool results are private or public
- fixture mode: `clean`, `noisy`, `stale`, `adversarial`, or `failure`
- fail-fast behavior for tool exceptions

Every tool event records arguments, result summaries, provenance, visibility,
latency/cost placeholders, and structured errors.

## Transaction Layer

Accepted deals can be settled through `TransactionPort`. The first fixture
simulator separates negotiated product price from:

- shipping
- tax
- escrow fees
- payment fees
- seller platform fees
- return and reputation risk
- payment failure

Transaction outcomes are recorded as public system events.

## Outputs

Each run directory contains:

- `manifest.json`
- `scenario.json`
- `trace.jsonl`
- `metrics.json`

The trace is the authoritative audit trail. Metrics are derived from the
scenario, outcome, trace, tool events, and transaction events.

## No-Key Smoke Benchmark

Run:

```bash
opennego run --config configs/no_key_smoke.yaml
```

The default smoke config runs one product scenario across five regimes:

- no tools
- buyer-private market search
- seller-private market search
- symmetric market search
- buyer-private market-search failure

All evidence is fixture-backed. No live marketplace, browser, payment, or
provider calls are made.
