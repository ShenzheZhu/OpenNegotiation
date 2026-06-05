# Benchmark Spec

OpenNego evaluates agent-to-agent negotiation as part of a broader transaction
workflow. The benchmark is intentionally provider-neutral: model access, tools,
and transaction systems are attached through ports.

## Run Unit

A run is one scenario x tool regime x seed x agent pair. The config runner
builds the Cartesian product declared in an experiment config and writes one
artifact directory per run.

## Scenario

The first scenario schema is product-centric and remains compatible with
A2A-NT-style records:

- product id, name, description, condition
- list or asking price
- legacy wholesale price, or a synthetic reservation-derived substitute for
  market-style fixtures
- optional market reference: reference price, robust spread, sample size,
  source, collection window, currency, and sale mechanism
- buyer budget
- seller reservation price
- max public turns
- optional metadata

A2A-NT-style product records can be loaded, but product resale is one domain,
not the whole framework.

For real-market C2C scenarios, OpenNego treats the observed sold-price
distribution as the external reference. Seller reservation remains a private
simulation constraint, not an observed human cost label. See
[Real-Market Benchmark Design](real_market_benchmark_design.md).

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
- return, reputation, and dispute risk
- deterministic payment, shipping, item-mismatch, return-window, and dispute
  guard failures

Transaction outcomes are recorded as public system events.

## Outputs

Each run directory contains:

- `manifest.json`
- `scenario.json`
- `trace.jsonl`
- `metrics.json`

The trace is the authoritative audit trail. Metrics are derived from the
scenario, outcome, trace, tool events, and transaction events.

Market-grounded runs additionally report:

- `market_reference_price`
- `market_price_gap`
- `normalized_market_gap`
- `buyer_savings_vs_market_reference`
- `seller_revenue_vs_market_reference`

Run directories can be aggregated with:

```bash
opennego leaderboard --input-dir runs/real_market_demo --output runs/leaderboard_summary.json
```

The generated `opennego.leaderboard.v1` artifact is the machine-readable
scorecard layer for local demos and external dashboards. It includes run-level
rankings plus separate buyer and seller role-track aggregates. This scorecard
track is deterministic and no-key; pairwise Elo-style arena tracks can be added
later once benchmark schedules include enough reciprocal matchups.

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

## Real-Market Demo Report

Run the tiny market-grounded demo and generate a static dashboard:

```bash
opennego run --config configs/real_market_demo.yaml --output-dir /tmp/opennego-real-market-demo
opennego report --input-dir /tmp/opennego-real-market-demo --output /tmp/opennego-real-market-demo.html
```

This demo uses one product cluster, three tool regimes, one seed, and no live
marketplace or model-provider calls.
