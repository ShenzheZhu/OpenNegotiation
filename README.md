<p align="center">
  <img alt="OpenNegotiation - A Real-Market Negotiation Gym for Agent-to-Agent Evaluation and Evolution" src="./docs/assets/opennegotiation-logo.svg" width="900">
</p>

<p align="center">
  <a href="#overview">Overview</a> ·
  <a href="#features">Features</a> ·
  <a href="#start-here">Start here</a> ·
  <a href="#documentation">Documentation</a> ·
  <a href="#examples">Examples</a> ·
  <a href="#citation">Citation</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square">
  <img alt="Local demo" src="https://img.shields.io/badge/local--demo-2d7d46?style=flat-square">
  <img alt="LLM gateway" src="https://img.shields.io/badge/LLM%20gateway-LiteLLM%20adapter-8f7f6b?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/status-research--preview-0d3b66?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-TBD-lightgrey?style=flat-square">
</p>

<h2 id="overview">Overview</h2>

OpenNegotiation is a real-market negotiation gym for agent-to-agent evaluation
and evolution. It helps teams benchmark, spar, and improve buyer/seller agents
in market-grounded scenarios with tool access, private constraints, transaction
rules, and traceable outcomes.

The repo is built around one shared gym core and two primary modes:

| Mode | Use it for | Main outputs |
| --- | --- | --- |
| Benchmark | Compare agents across buyer/seller roles and market scenarios | traces, metrics, scorecards, leaderboard summaries |
| Sparring and evolution | Pit a user agent against curated NPC counterparties | battle reports, failure analysis, strategy patch candidates |

OpenNegotiation is meant to be used as research infrastructure, not a static
prompt demo. Agents can inspect market evidence, call typed tools, keep private
state private, negotiate under transaction constraints, and leave behind
versioned artifacts that can be audited or reused for policy improvement.

<h2 id="features">Features</h2>

- Market-grounded negotiation scenarios with product fixtures, sold-comps
  references, private budgets, seller targets, fees, and transaction terms.
- Provider-neutral `AgentPort`, `ToolPort`, and `LLMPort` contracts, with live
  model runs routed through a LiteLLM adapter outside the core environment.
- Role-swapped benchmark tracks so a participant can be evaluated as both buyer
  and seller before leaderboard aggregation.
- Tool-aware trace logging that preserves messages, offers, tool calls,
  transaction events, provenance, and private/shared visibility boundaries.
- Curated NPC strategy profiles for sparring, failure diagnosis, and
  strategy-layer prompt improvement.
- Local strategy marketplace primitives for sharing, validating, and installing
  reusable negotiation profiles.
- Deterministic local demo paths plus full live-validation hooks for model
  providers and official real-market data adapters.

<h2 id="start-here">Start Here</h2>

Install the local package:

```bash
git clone https://github.com/Kordi-AI/OpenNegotiation.git
cd OpenNegotiation
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the complete local demo:

```bash
opennego demo \
  --output-dir /tmp/opennegotiation-demo \
  --report /tmp/opennegotiation-demo.html

opennego validate-demo \
  --manifest /tmp/opennegotiation-demo/demo_manifest.json
```

Run the minimal smoke benchmark:

```bash
opennego run --config configs/no_key_smoke.yaml
```

For detailed commands, configuration fields, live model setup, and handoff
packages, use the documentation map below.

<h2 id="documentation">Documentation</h2>

| I want to... | Read |
| --- | --- |
| Understand the system architecture | [Architecture](docs/architecture.md) |
| Run config-driven experiments | [Experiment Runner](docs/experiment_runner.md) |
| Connect my own agent or local factory | [Agent Integration](docs/agent_integration.md) |
| Run LLM-backed baselines through LiteLLM | [LLM Baselines](docs/llm_baselines.md) |
| Understand benchmark artifacts and scoring | [Benchmark Contract](docs/benchmark_contract.md) and [Benchmark Spec](docs/benchmark_spec.md) |
| Plan reciprocal buyer/seller evaluations | [Benchmark Contract](docs/benchmark_contract.md) |
| Use NPC sparring and policy learning | [Policy Learning](docs/policy_learning.md) |
| Work with strategy marketplace profiles | [Policy Learning](docs/policy_learning.md) |
| Inspect transaction simulation rules | [Transaction Simulator](docs/transaction_simulator.md) |
| Design real-market C2C evaluation data | [Real-Market Benchmark Design](docs/real_market_benchmark_design.md) |
| Validate source policy and live collection boundaries | [Live Validation Notes](docs/live_validation_102.md) |
| Prepare an external demo or handoff bundle | [Demo Readiness](docs/demo_readiness.md) and [Release Checklist](docs/release_checklist.md) |
| Debug setup, parser, or CLI issues | [Troubleshooting](docs/troubleshooting.md) |
| Track research directions and open product gaps | [Research Agenda](docs/research_agenda.md) |

<h2 id="examples">Examples</h2>

Curated demo artifacts are committed for quick inspection:

| Artifact | Link |
| --- | --- |
| Full demo report | [examples/reports/full_demo.html](examples/reports/full_demo.html) |
| Benchmark report | [examples/reports/benchmark_demo.html](examples/reports/benchmark_demo.html) |
| Demo run summary | [examples/outputs/demo_run_summary.json](examples/outputs/demo_run_summary.json) |
| Private market-search metrics | [examples/outputs/buyer_private_market_search_metrics.json](examples/outputs/buyer_private_market_search_metrics.json) |

<h2 id="repository-map">Repository Map</h2>

| Path | Purpose |
| --- | --- |
| [src/opennego/](src/opennego/) | core package, ports, adapters, agents, tools, transactions, metrics |
| [configs/](configs/) | local fixture and live-validation experiment configs |
| [examples/data/](examples/data/) | small fixtures and NPC strategy registry |
| [examples/reports/](examples/reports/) | curated static HTML reports |
| [docs/](docs/) | implementation details, contracts, integration guides, release notes |
| [tests/](tests/) | deterministic regression tests |

<h2 id="citation">Citation</h2>

Citation information will be added with the first public paper or technical
report release.

<h2 id="license">License</h2>

TBD.
