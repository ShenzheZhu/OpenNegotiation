<p align="center">
  <img alt="OpenNegotiation - A Real-Market Negotiation Gym for Agent-to-Agent Evaluation and Evolution" src="./docs/assets/opennegotiation-logo.svg" width="900">
</p>

<p align="center">
  <a href="#why-opennegotiation">Why</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="#workflows">Workflows</a> ·
  <a href="#cli-reference">CLI</a> ·
  <a href="#documentation">Docs</a> ·
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <a href="https://github.com/Kordi-AI/OpenNegotiation/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Kordi-AI/OpenNegotiation/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-2d7d46?style=flat-square">
  <img alt="Status" src="https://img.shields.io/badge/status-research--preview-0d3b66?style=flat-square">
</p>

**OpenNegotiation** is a negotiation gym for AI agents. It runs buyer and
seller agents against each other in market-grounded consumer-to-consumer
scenarios — with real sold-comparable price evidence, typed tools, private
budgets and reservation prices, transaction settlement rules, and fully
auditable traces — then turns the results into leaderboards, failure
diagnoses, and concrete strategy improvements.

## Why OpenNegotiation

Most negotiation benchmarks are static prompt exchanges. OpenNegotiation
treats negotiation as an *agentic* task: what changes when agents can gather
market evidence, reason about fees and risk, and settle deals under realistic
transaction constraints?

- **Market-grounded scenarios.** Products carry sold-comps references
  (median, quartiles, sample size, recency) ingested from offline exports or
  the official eBay Marketplace Insights API — never scraped data.
- **Tool regimes as the experimental variable.** Run the same scenario with
  no tools, buyer-only search, symmetric search, or noisy/stale/adversarial
  market data, and measure how outcomes shift.
- **Private state stays private.** Budgets, reservation prices, and private
  tool calls are visible only to the owning agent, but everything is recorded
  in the trace for post-hoc audit.
- **Realistic settlement.** Deals settle through a transaction simulator with
  shipping, tax, escrow and payment fees, return windows, delivery SLAs,
  warranty and compliance guards — a deal that violates a buyer's all-in cost
  cap or a seller's net-revenue floor fails.
- **Closed improvement loop.** Sparring against curated NPC archetypes
  produces battle reports, trace-grounded lessons, versioned strategy
  candidates, and before/after comparisons.
- **Provider-neutral core.** Agents, tools, LLM gateways, and transactions
  are ports; LiteLLM and eBay integrations are adapters. Everything runs
  deterministically without API keys by default.

## Quickstart

Requires Python 3.10+.

```bash
git clone https://github.com/Kordi-AI/OpenNegotiation.git
cd OpenNegotiation
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the complete local demo (benchmark + leaderboard + policy learning +
HTML report), then validate the bundle — no API keys needed:

```bash
opennego demo --output-dir runs/demo --report runs/demo/report.html
opennego validate-demo --manifest runs/demo/demo_manifest.json
```

Run the five-scenario smoke benchmark:

```bash
opennego run --config configs/no_key_smoke.yaml
```

Every run writes four versioned artifacts — `scenario.json`,
`manifest.json`, `trace.jsonl`, `metrics.json` — which all downstream
layers (leaderboards, reports, learning) consume. See the
[Benchmark Contract](docs/benchmark_contract.md) for the schema.

## Workflows

### Benchmark agents

Compare agents across tool regimes and roles, then aggregate:

```bash
opennego run --config configs/real_market_demo.yaml --output-dir runs/bench
opennego leaderboard --input-dir runs/bench --output runs/bench/leaderboard_summary.json
opennego report --input-dir runs/bench --output runs/bench/report.html
opennego role-swap --participant-id my_strategy   # evaluate both roles
```

To benchmark live models, install the LLM extra and use `llm_buyer` /
`llm_seller` agent kinds in your config ([LLM Baselines](docs/llm_baselines.md)):

```bash
python -m pip install -e ".[dev,llm]"
export OPENROUTER_API_KEY=...   # or OPENAI_API_KEY / ANTHROPIC_API_KEY
opennego run --config configs/llm_pair.example.yaml
```

### Spar and improve a strategy

Pit your agent against curated NPC archetypes (hardline anchors, stale-comps
sellers, hidden-fee sellers), diagnose failures, and iterate:

```bash
opennego strategies                          # list NPC profiles
opennego spar --output-dir runs/spar --report runs/spar/report.html
opennego train --output-dir runs/train      # full spar -> patch -> rerun loop
```

`train` produces a versioned strategy candidate plus a before/after
comparison. Apply it and export it for your own agent stack:

```bash
opennego apply-strategy --candidate runs/train/strategy_candidate.json \
  --output runs/train/strategy_config.json
opennego export-training-adapter --strategy-config runs/train/strategy_config.json \
  --agent-kind my_agent --output runs/train/adapter.json
```

Your own agents plug in through `AgentPort` factories — from the CLI
(`--agent-factory`, `--user-agent-factory`) or the Python API
([Agent Integration](docs/agent_integration.md)).

### Build market datasets

Normalize sold-comps evidence into validated scenario fixtures, gated by
explicit source policies (collection mode, data rights, privacy boundaries):

```bash
opennego ingest-market --input my_sold_comps.csv \
  --products-output data/products.json --comps-output data/market_comps.json \
  --manifest-output data/manifest.json
opennego validate-market --products-file data/products.json \
  --market-comps-file data/market_comps.json --manifest-file data/manifest.json
```

Then turn a validated dataset into a runnable multi-category scenario pack
with BATNA-derived private constraints:

```bash
opennego scenarios build --products-file data/products.json \
  --market-comps-file data/market_comps.json --output-dir packs/my_pack --seed 13
opennego run --config packs/my_pack/experiment_config.json
```

Live ingestion uses the official eBay Marketplace Insights API
([guide](docs/github_actions_ingestion.md) for the scheduled GitHub Actions
version).

## CLI Reference

`opennego help` prints the full list. Commands emit structured JSON and use
exit codes `0` (success), `1` (completed with failures), `2` (usage error).

| Group | Commands |
| --- | --- |
| Benchmark | `run`, `report`, `leaderboard`, `role-swap`, `arena-plan`, `arena-run` |
| Demo | `demo`, `validate-demo`, `run-models` |
| Sparring & learning | `strategies`, `spar`, `learn`, `evolve`, `compare`, `train`, `apply-strategy`, `export-training-adapter`, `validate-training-adapter` |
| Market data | `market-source-policy`, `validate-market-source`, `ingest-market`, `ingest-ebay`, `ingest-ebay-active`, `validate-market`, `scenarios` |
| Strategy marketplace | `marketplace-export`, `validate-marketplace` |

## Documentation

| I want to... | Read |
| --- | --- |
| Understand the system design and boundaries | [Architecture](docs/architecture.md) |
| Run config-driven experiments | [Experiment Runner](docs/experiment_runner.md) |
| Connect my own agent | [Agent Integration](docs/agent_integration.md) |
| Run LLM-backed baselines through LiteLLM | [LLM Baselines](docs/llm_baselines.md) |
| Understand artifacts and scoring | [Benchmark Contract](docs/benchmark_contract.md), [Benchmark Spec](docs/benchmark_spec.md) |
| Use NPC sparring and policy learning | [Policy Learning](docs/policy_learning.md) |
| Inspect transaction settlement rules | [Transaction Simulator](docs/transaction_simulator.md) |
| Design real-market evaluation data | [Real-Market Benchmark Design](docs/real_market_benchmark_design.md) |
| Schedule automated eBay ingestion | [GitHub Actions Ingestion](docs/github_actions_ingestion.md) |
| See the product roadmap and design decisions | [Roadmap](docs/roadmap.md) |
| Debug setup or CLI issues | [Troubleshooting](docs/troubleshooting.md) |

Curated example artifacts: [full demo report](examples/reports/full_demo.html),
[benchmark report](examples/reports/benchmark_demo.html),
[run summary](examples/outputs/demo_run_summary.json).

## Repository Map

| Path | Purpose |
| --- | --- |
| [src/opennego/](src/opennego/) | core environment, ports, adapters, agents, tools, transactions, metrics |
| [src/opennego/cli/](src/opennego/cli/) | CLI command modules grouped by surface |
| [configs/](configs/) | fixture and live experiment configs |
| [examples/](examples/) | small data fixtures, NPC registry, curated reports |
| [docs/](docs/) | architecture, contracts, and integration guides |
| [tests/](tests/) | deterministic regression tests (no API keys required) |

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
development workflow, design rules, and the no-key check gate that every
change must pass. Notable changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## Citation

Citation information will be added with the first public technical report. In
the meantime, please link to this repository.

## License

[Apache-2.0](LICENSE) © Kordi AI
