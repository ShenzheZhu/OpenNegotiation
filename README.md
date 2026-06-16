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

**OpenNegotiation** is a training gym for marketplace agents. Bring your own
buyer or seller agent — any model through LiteLLM plus your own strategy
prompt — and train it against calibrated opponents on real-market data: spar,
get a coach's battle report, evolve the strategy prompt with evidence, climb
an Elo-style ladder, and finally turn it loose in a concurrent eBay-style
market sandbox. Everything runs deterministically with no API keys by default.

## Why OpenNegotiation

Most negotiation benchmarks are static prompt exchanges. OpenNegotiation
treats negotiation as an *agentic* task and closes the loop from evaluation to
improvement:

- **Market-grounded scenarios.** Products carry sold-comps references
  (median, quartiles, sample size, recency) ingested from offline exports or
  the official eBay APIs — never scraped data. Buyer budgets and seller
  reservations derive from real outside options (BATNA), not hand-picked
  constants.
- **An LLM coach that can't cheat.** After a match, a coach (deterministic by
  default, or BYOK-LLM) writes a battle report — decision points,
  counterfactuals, weaknesses by phase, a safety verdict. It sees only what
  your agent could see; the counterpart's private state never reaches it, so
  evolved strategies transfer to real markets.
- **Prompt evolution, not weight training.** The coach proposes strategy-layer
  edits on top of a fixed base protocol; held-out NPC validation flags
  overfit candidates before you adopt them, and every version is tracked in a
  lineage.
- **Ratings that mean something.** Per-match normalized surplus feeds a
  continuous Bradley-Terry ladder with separate buyer and seller tracks;
  engaging a scam zeroes the score, so a price-only optimizer that ignores
  safety ranks last.
- **A real market sandbox.** Skill drills (selection, walk-away, multi-thread,
  quality, reputation) train competencies in isolation; a concurrency scheduler
  then runs many buyer-seller threads at once with clearing, staged autonomy
  L1–L3, and a calibration report that checks the sandbox against real eBay
  distributions.
- **Information asymmetry, priced in.** A seller can hide an item's true
  condition behind a public claim; the buyer spends a turn on the `inspect`
  tool for a noisy private quality estimate. Seller reputation is the opposite
  kind of signal — public but noisy. Both feed the score: overpaying for a
  lemon or a low-feedback seller wipes out buyer surplus, and a seller who
  exploited the gap carries the dispute exposure.
- **Local web client.** `opennego serve` gives a browser UI for the whole
  loop; your API key is sent only to the local server and never stored.
- **Provider-neutral, zero-dependency core.** Agents, tools, LLM gateways, and
  transactions are ports; LiteLLM and eBay integrations are adapters. The
  Python package has no runtime dependencies.

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
comparison, and `--holdout-validation` reruns the candidate against opponents
it never trained on so an overfit (`train_only`) patch is flagged before you
adopt it. Apply it (recording a lineage), then export it for your own stack:

```bash
opennego apply-strategy --candidate runs/train/strategy_candidate.json \
  --output runs/train/strategy_config.json --lineage runs/train/lineage.json
opennego lineage --lineage runs/train/lineage.json
opennego export-training-adapter --strategy-config runs/train/strategy_config.json \
  --agent-kind my_agent --output runs/train/adapter.json
```

For a single run, `opennego learn` writes the coach battle report (rules by
default, or `--coach llm --coach-model <id>` to use your own model), and
`opennego evolve` / `opennego compare` drive the candidate and before/after
diff directly. Your own agents plug in through `AgentPort` factories — from the
CLI (`--agent-factory`, `--user-agent-factory`) or the Python API
([Agent Integration](docs/agent_integration.md)).

### Rate agents in an arena

Score completed runs as normalized surplus and rank participants on buyer and
seller rating tracks with uncertainty:

```bash
opennego arena-plan --participant my_strategy --participant baseline \
  --output runs/arena/plan.json
opennego arena-run --plan runs/arena/plan.json --store runs/arena/ratings.db
opennego leaderboard --store runs/arena/ratings.db --report runs/arena/ratings.html
```

### Train market skills and run the sandbox

Drill individual market skills, then run the concurrent market:

```bash
opennego drill select        # pick the most attainable deal (reputation traps)
opennego drill walkaway      # cut losses fast, but not on a real concession
opennego drill multithread   # shop competing threads vs working one listing
opennego drill quality       # inspect a lemon and discount, vs paying the claim
opennego drill reputation    # discount a low-feedback seller, vs ignoring it
opennego market-run --buyer me --buyer rival   # concurrent threads + clearing
opennego market-run --level L2                 # staged autonomy L1/L2/L3
opennego market-calibrate                       # sandbox vs real-market distributions
```

### Use the local web client

```bash
cd web && npm install && npm run build   # build the React + EUI client once
opennego serve                            # http://127.0.0.1:8765
```

Define your agent (model + strategy prompt; the API key is sent only to the
local server and never stored), run matches, read the coach report, accept or
reject an evolved strategy, and watch your ratings — the whole loop in the
browser. See [the web client section](#local-web-client) below.

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
| Client | `serve` |
| Market skills | `drill`, `market-run`, `market-calibrate` |
| Sparring & learning | `strategies`, `spar`, `learn`, `evolve`, `compare`, `train`, `apply-strategy`, `lineage`, `export-training-adapter`, `validate-training-adapter` |
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
| Understand the coach and battle report v2 | [Coach design](docs/design/coach.md) |
| Understand ratings and the arena | [Rating design](docs/design/rating.md) |
| Understand the market sandbox | [Market design](docs/design/market.md) |
| Understand hidden condition and seller reputation | [Information asymmetry design](docs/design/information_asymmetry.md) |
| Run the local web client | [Serve design](docs/design/serve.md) |
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
| [src/opennego/serve/](src/opennego/serve/) | stdlib HTTP backend for the local web client |
| [web/](web/) | React + Elastic UI client (Vite, TypeScript) |
| [configs/](configs/) | fixture and live experiment configs |
| [examples/](examples/) | small data fixtures, NPC registry, curated reports |
| [docs/](docs/) | architecture, contracts, and integration guides |
| [tests/](tests/) | deterministic regression tests (no API keys required) |

### Local web client

```bash
cd web && npm install && npm run build   # build the React + EUI client once
opennego serve                            # serve it at http://127.0.0.1:8765
```

The Python package has no JS runtime dependency; the client is a separate
build under `web/`. Without a build, `opennego serve` shows a placeholder
explaining the step. Your API key is sent only to the local server and is
never written to disk or returned by any endpoint.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
development workflow, design rules, and the no-key check gate that every
change must pass. Notable changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## Citation

Citation information will be added with the first public technical report. In
the meantime, please link to this repository.

## License

[Apache-2.0](LICENSE) © Kordi AI
