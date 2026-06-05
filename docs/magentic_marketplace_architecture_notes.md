# Magentic Marketplace Architecture Notes

Reviewed sources:

- Paper: [Magentic Marketplace: An Open-Source Environment for Studying Agentic
  Markets](https://arxiv.org/abs/2510.25779)
- Repository: [microsoft/multi-agent-marketplace](https://github.com/microsoft/multi-agent-marketplace)
- Microsoft Foundry Labs overview:
  [Magentic Marketplace](https://labs.ai.azure.com/innovations/magentic-marketplace/)

This note records what OpenNego should learn from Magentic Marketplace without
copying its code or narrowing OpenNego into an MSR-specific benchmark adapter.
The goal is a broader agent-to-agent negotiation and transaction gym for
realistic application markets.

## Takeaways

Magentic Marketplace is stronger than a static two-agent negotiation setup
because it models an end-to-end market lifecycle:

1. Agent registration.
2. Protocol discovery.
3. Action execution.
4. Search and discovery.
5. Agent-to-agent communication.
6. Structured order proposals.
7. Payment and transaction completion.
8. Analytics over actions, messages, proposals, payments, and LLM calls.

The important architectural pattern is not a specific restaurant dataset or a
specific prompt. The important pattern is that agents interact with a market
runtime through typed actions, while the runtime controls search, messaging,
transaction integrity, persistence, and evaluation.

## What OpenNego Should Adopt

### Protocol First

OpenNego should move from a buyer-seller prompt loop toward a typed market
protocol. A protocol should declare available capabilities and accept action
objects such as:

- `Search`: discover counterparties, products, services, or comps.
- `FetchMessages`: retrieve asynchronous messages for an agent.
- `SendMessage`: send free-form negotiation text.
- `SubmitOffer`: send a structured price, quantity, constraint, or bundle offer.
- `AcceptOffer`: commit to an offer.
- `SendPayment`: attempt payment or escrow.
- Future actions: `Refund`, `Dispute`, `Review`, `VerifyIdentity`,
  `RequestShippingQuote`, and `InspectReputation`.

The first OpenNego implementation can stay in-process and fixture-backed, but
the action schema should be runtime-neutral so a future HTTP server does not
require a benchmark rewrite.

### Runtime Layers

OpenNego should keep these layers separate:

- `AgentPort`: agent decision logic, whether scripted, LLM-backed, or external.
- `LLMPort`: provider-neutral model access through LiteLLM adapters.
- `ToolPort`: private or shared tools such as market comps and reputation
  lookup.
- `MarketProtocol`: typed actions and action validation.
- `MarketRuntime`: state transitions, message routing, search, and transaction
  execution.
- `ArtifactStore`: append-only traces, manifests, scenarios, metrics, and
  future structured action logs.

This keeps the core gym provider-neutral while making external runtimes,
databases, and model providers replaceable.

### Full Lifecycle Metrics

OpenNego metrics should extend beyond final price:

- Search quality: relevant counterparties returned, ranking effects, and
  missed optimal candidates.
- Negotiation behavior: number of messages, concessions, anchoring, bluffing,
  deadlocks, and invalid commitments.
- Proposal validity: nonexistent products, malformed prices, inconsistent
  totals, expired offers, or impossible fulfillment terms.
- Transaction realism: payment success, escrow, shipping, tax, returns,
  warranties, and disputes.
- Market outcomes: buyer utility, seller utility, welfare, deal rate,
  completion rate, and fairness across counterparties.
- Agent robustness: tool failures, stale information, manipulation, prompt
  injection, first-proposal bias, search-position bias, and latency bias.
- Cost and observability: LLM call counts, tool call counts, latency, token
  usage, provider/model metadata, and failures.

### Data Model

Magentic Marketplace's customer/business split maps well to OpenNego, but
OpenNego should keep the schema domain-general:

- `PrincipalProfile`: human or organization represented by the agent.
- `AgentProfile`: role, capabilities, and private instructions for the agent.
- `NeedSpec`: buyer request, constraints, budget, utility model, and risk
  tolerance.
- `OfferCatalog`: seller products/services, inventory, constraints, reserve
  prices, reputation, and fulfillment terms.
- `MarketScenario`: domain, agents, counterparties, tools, search index,
  transaction rules, and expected oracle data.

Domains should include consumer resale, service procurement, travel, retail,
contracting, and synthetic controlled markets. A2A-NT-style product negotiation
should become one domain, not the whole framework.

### Infrastructure Path

OpenNego does not need to start with a production server stack. The pragmatic
path is:

1. In-process runtime with typed actions and JSON/JSONL artifacts.
2. Config-driven runner for model x scenario x regime sweeps.
3. SQLite artifact export for scalable analytics.
4. Optional HTTP runtime with register/protocol/action endpoints.
5. Optional Postgres-backed server mode for high-concurrency agent experiments.

This path gives MSR and other model teams a usable benchmark quickly, while
keeping the design compatible with industrial deployment patterns.

## What OpenNego Should Not Copy

- Do not import or adapt Magentic Marketplace source code directly.
- Do not build around one restaurant/contractor schema.
- Do not make OpenNego a compatibility wrapper for their CLI.
- Do not prematurely require Docker, Postgres, or FastAPI for local benchmark
  runs.
- Do not hide benchmark behavior inside prompts. Actions, tools, search results,
  transactions, and violations must be structured and auditable.
- Do not make the benchmark MSR-facing only. The public framing should be
  broader: agentic negotiation and transaction evaluation for application
  markets.

## Consequences For Current Issues

### #5 Config-Driven Experiment Runner

The runner should accept scenario files, model configs, tool regimes, search
regimes, seeds, output directories, and run labels. It should emit the existing
artifact contract and be shaped so future action logs can be added without
breaking old runs.

### #6 LLM Baselines

Baselines should include no-tool and tool-aware agents behind `AgentPort`, using
`LLMPort` for model access. Live provider tests should be optional; CI should
use deterministic fake LLM gateways and fixture-backed tools.

### #7 Tool And Information Regimes

Regimes should model both information access and market protocol access:

- no tools;
- private buyer tools;
- private seller tools;
- symmetric tools;
- noisy or stale tools;
- adversarial or manipulated tools;
- search-only;
- search plus negotiation;
- search plus negotiation plus transaction.

### #8 Benchmark Release Package

The release should include a clear install path, sample configs, a deterministic
smoke run, artifact contract docs, expected output examples, and guidance for
plugging in external model providers through LiteLLM without committing secrets.

### #9 Transaction Simulator

The simulator should start with structured offers, acceptances, and payments,
then grow toward escrow, shipping, taxes, returns, warranties, reputation, and
disputes. It should validate proposal consistency before computing utility.

## Suggested OpenNego Architecture

```mermaid
flowchart LR
  subgraph "Agents"
    "Buyer Agent"
    "Seller Agent"
    "External Agent"
  end

  subgraph "Ports"
    "AgentPort"
    "LLMPort"
    "ToolPort"
  end

  subgraph "Market Core"
    "MarketProtocol"
    "MarketRuntime"
    "Transaction Simulator"
    "Search/Tool Regimes"
  end

  subgraph "Outputs"
    "Scenario Artifact"
    "Run Manifest"
    "Trace JSONL"
    "Metrics Report"
    "Future SQLite Export"
  end

  "Buyer Agent" --> "AgentPort"
  "Seller Agent" --> "AgentPort"
  "External Agent" --> "AgentPort"
  "AgentPort" --> "LLMPort"
  "AgentPort" --> "ToolPort"
  "AgentPort" --> "MarketProtocol"
  "MarketProtocol" --> "MarketRuntime"
  "ToolPort" --> "Search/Tool Regimes"
  "MarketRuntime" --> "Transaction Simulator"
  "MarketRuntime" --> "Trace JSONL"
  "Transaction Simulator" --> "Metrics Report"
  "MarketRuntime" --> "Run Manifest"
  "MarketRuntime" --> "Scenario Artifact"
  "Trace JSONL" --> "Future SQLite Export"
```

## Near-Term Priority

The fastest credible path for next-week external testing is:

1. Finish #5 so a model team can run repeatable sweeps from config files.
2. Finish #6 with at least one deterministic LLM baseline path and one
   tool-aware baseline path.
3. Finish #7 enough to compare no-tool, private-tool, symmetric-tool, and noisy
   tool regimes.
4. Finish the first slice of #9 with structured offers and payment validation.
5. Package #8 with examples, run instructions, and artifact interpretation.

Server mode, Postgres, and a UI should remain planned but not on the critical
path for the first serious benchmark handoff.
