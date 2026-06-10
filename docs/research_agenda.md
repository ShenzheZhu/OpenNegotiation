# OpenNegotiation Research Agenda

OpenNegotiation starts from the A2A-NT consumer negotiation setup and asks what changes
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
- Route LLM-backed agents through a formal `LLMPort`; use LiteLLM as the
  preferred gateway adapter for provider coverage, routing, and cost metadata.
- Keep tool traces auditable.
- Separate private information from public dialogue.
- Make no-tool and tool-using settings directly comparable.
- Preserve deterministic fixtures for tests even when live tools are added.
- Treat transaction safety as part of the task, not only as post-hoc labeling.

## Architecture Reference Pass

OpenNegotiation should learn from mature agentic market simulators such as
[Magentic Marketplace](https://arxiv.org/abs/2510.25779), but it should not
become a compatibility wrapper for one paper or one synthetic marketplace.

The key design shift is to treat negotiation as one phase in a broader market
lifecycle:

1. Agent registration and capability discovery.
2. Search and information gathering.
3. Agent-to-agent communication and negotiation.
4. Structured offers, acceptances, and payments.
5. Transaction validation and utility computation.
6. Artifact-backed analytics and replay.

## Near-Term Roadmap

1. Add a config-driven experiment runner for model x scenario x tool-regime
   sweeps.
2. Add no-tool and tool-aware LLM baselines behind `AgentPort` and `LLMPort`.
3. Add explicit information and tool regimes, including private, symmetric,
   noisy, stale, and adversarial tool settings.
4. Add protocol-level action models for search, messages, structured offers,
   acceptances, and payments.
5. Add richer anomaly labels for overpayment, constraint violation, invalid
   proposals, deadlocks, payment failure, and tool-induced failures.
6. Add dataset loaders for A2A-NT-style product JSON and domain-general market
   scenario files.
7. Add provenance-aware live market search behind an offline-cache interface.
8. Add an optional server runtime only after the in-process benchmark contract is
   stable.
