# OpenNego Research Agenda

OpenNego starts from the A2A-NT consumer negotiation setup and asks what changes
when agents can use tools before and during negotiation.

## Central Question

How do agentic capabilities change negotiation outcomes, safety risks, and
market efficiency in agent-to-agent consumer transactions?

The core hypothesis is that tool use changes the game. A buyer agent with access
to recent comparable sales should negotiate differently from a buyer relying
only on model priors. A seller agent with listing analytics, fraud signals, or
inventory pressure should also behave differently.

## Evaluation Axes

- Information regime: no tool, static retrieval, live search, private tools,
  asymmetric tools, and shared tools.
- Tool reliability: exact data, noisy data, stale data, manipulated data, and
  unavailable tools.
- Negotiation objective: lowest price, highest seller margin, welfare,
  successful transaction, constraint compliance, or risk minimization.
- Transaction realism: price-only deal, shipping cost, escrow, payment failure,
  returns, reputation, warranties, and add-ons.
- Agent autonomy: single prompt response, multi-step planning, tool use,
  memory, and delegated subtasks.
- Strategic behavior: bluffing, selective disclosure, anchoring, persuasion,
  collusion, deception, and policy violations.

## Initial Benchmarks

1. Static A2A baseline with no tools.
2. Buyer-only market-search setting.
3. Seller-only market-search setting.
4. Symmetric market-search setting.
5. Noisy or adversarial comparable-sales setting.

Each benchmark should report deal rate, normalized price, buyer savings, seller
profit, welfare, budget violations, reservation-price violations, deadlocks, and
tool-call cost.

## Tool Ladder

- Fixture-backed market comparable search.
- Retrieval over curated product and transaction datasets.
- Browser/search tool with source provenance.
- Product verification and seller reputation tools.
- Shipping, tax, escrow, payment, and return-policy simulators.
- Transaction execution sandbox.

## Design Principles

- Keep the environment provider-neutral.
- Keep tool traces auditable.
- Separate private information from public dialogue.
- Make no-tool and tool-using settings directly comparable.
- Preserve deterministic fixtures for tests even when live tools are added.
- Treat transaction safety as part of the task, not only as post-hoc labeling.

## Near-Term Roadmap

- Add LLM agent adapters behind the `NegotiationAgent` protocol.
- Add a dataset loader for A2A-NT-style product JSON.
- Add richer anomaly labels for overpayment, constraint violation, deadlock, and
  tool-induced failures.
- Add experiment runners for model x tool-regime sweeps.
- Add provenance-aware live market search behind an offline-cache interface.
