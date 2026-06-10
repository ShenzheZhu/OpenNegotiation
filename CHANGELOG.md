# Changelog

All notable changes to OpenNegotiation are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Restructured the CLI from a single module into `opennego.cli` command
  packages grouped by surface (benchmark, demo, learning, market,
  marketplace). All command names and outputs are unchanged; `opennego help`
  now lists every command.
- Licensed the project under Apache-2.0 and added packaging metadata.
- Rewrote the README and documentation set around the supported workflows.

### Removed

- Legacy `mvp-demo` command and the `opennego.mvp_demo` compatibility shim.
  Use `opennego demo`; bundle manifests now only use `opennego.demo_bundle.v1`.
- `opennego handoff` external package generator. The repository itself is the
  handoff: `opennego demo` plus `opennego validate-demo` covers the same
  surface.
- Internal bootstrap process notes (agent progress log, demo readiness audit,
  live validation records, naming policy) from `docs/`.

## [0.1.0] - 2026-06-05

### Added

- Core negotiation environment with private tool traces, typed actions, and
  transaction settlement (`opennego.benchmark.v1` artifacts).
- Config-driven experiment runner with resume support and no-key smoke
  configs.
- Provider-neutral ports (`AgentPort`, `ToolPort`, `LLMPort`,
  `TransactionPort`) with a LiteLLM adapter for live model runs.
- Market-grounded scenarios: sold-comps references, market price search tool
  regimes (clean/noisy/stale/adversarial), and fixture transaction terms.
- Sparring suites against curated NPC strategy profiles, policy-learning
  battle reports, strategy candidates, and before/after comparisons.
- Leaderboard aggregation, role-swapped benchmark tracks, and reciprocal
  arena planning.
- Offline sold-comps ingestion plus an official eBay Marketplace Insights
  adapter gated by market source policies.
- Static HTML reports for demo bundles and sparring suites.
