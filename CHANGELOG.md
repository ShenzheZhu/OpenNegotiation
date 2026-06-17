# Changelog

All notable changes to OpenNegotiation are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Co-evolution (M9, in progress): `opennego.coevolution` adds an evolvable strategy genome — a bounded numeric point in the deterministic policy space (buyer: `opening_discount`/`counter_fraction`/`willingness_multiplier`/`quality_skepticism`; seller: `opening_markup`/`concession_fraction`/`floor_reference_multiplier`). A genome maps to a real `BuyerPolicy`/`SellerPolicy` and drives a deterministic agent (via a new `policy_override` on the profile agents), with seeded, bounded `mutate` and per-gene `crossover`. The substrate for the no-key arms race.

- Co-evolution (M9, in progress): `opennego.coevolution.run_coevolution` runs the competitive engine — two populations (buyers, sellers) play a full tournament each generation (scored by the quality/reputation-aware match score), elites survive, and the rest are refilled by mutation/crossover for `G` generations. Emits `opennego.coevolution.v1` with per-generation leaderboards, the champion genome per role, the champion lineage, and the fitness trajectory. Deterministic in the seed; an `evolve` option can hold one role fixed (making the other's improvement monotone).

- Training season (M8, in progress): `opennego.training_season.aggregate_weaknesses` reads every battle report from a sparring suite and aggregates the coach's findings by `(phase, category)` into a ranked `opennego.weakness_profile.v1` — frequency across opponents, severity weight, mean policy score, and example opponent archetypes, ranked by `frequency * severity_weight * (1 - mean_score)`. The diagnostic that drives the validated candidate slate.

- Training season (M8, in progress): `opennego.training_season.run_training_season` turns the ranked weaknesses into a held-out-validated menu. It spars the whole opposite-role roster, and for the top-`k` weaknesses synthesizes a focused battle report, generates a targeted strategy candidate, reruns the suite with it, and records the held-out generalization verdict. Candidates are ranked with overfit (`train_only`/`regressed`) demoted below any that generalize, with an advisory recommendation and a baseline→best trajectory, emitted as `opennego.training_season.v1`. Nothing is auto-applied.

- Training season (M8, in progress): `opennego train-season` runs a season end to end (`--role`, `--k`, `--holdout-seed`, optional `--report` for a static HTML season report rendering the ranked weakness profile and validated candidate slate).

## [0.2.0] - 2026-06-16

The realistic-gym release: milestones M1–M7 on top of the 0.1.0 core — gym-core
realism, coach and prompt evolution, the rating arena, the local web client,
the market sandbox, and the information-asymmetry track (hidden condition and
public reputation).

### Added

- Reputation visibility (M7): a public seller-reputation signal. New `opennego.reputation` module is the single source of truth for the band vocabulary and its realized-value risk weight (`{high:0, medium:0.06, low:0.18, unknown:0.10}`, the weights the M5 selection drill already used, now consolidated) plus `band_from_feedback_pct` (shared with the eBay Browse adapter). `Scenario.seller_reputation` (`SellerReputation`: band + optional feedback pct/count) is **public** — visible to both roles through the scenario, the opposite of the hidden condition — round-trips through `ScenarioArtifact`, and is carried from a product record by the scenario generator. Fully additive.

- Reputation visibility (M7): `compute_match_score` is now reputation-aware. A `reputation_band` argument applies a public haircut to the same realized value the quality score uses (`* (1 - reputation_risk(band))`), so a low-reputation seller is a worse deal at the same price — the buyer loses surplus and the seller carries the dispute exposure of a buyer who overpaid. Threaded through arena / market / serve from `scenario.seller_reputation`. Fully additive: an omitted or `high` band is identical to before.

- Reputation visibility (M7): two reputation NPC archetypes — `reputation_premium_seller` (defends a justified premium, anchors high, cites its track record) and `reputation_discount_buyer` (reads `scenario.seller_reputation` and lowers willingness by the band's risk weight, demanding a discount from low-feedback sellers). Curated registry profiles added to `examples/data/npc_strategies.json` with provenance.

- Reputation visibility (M7): a `reputation` skill drill (`opennego drill reputation`, `opennego.skill_drill.v1`). It runs the same buyer twice against a low-reputation seller, once discounting for the public band and once ignoring it, scores both with the reputation-aware match score, and reports the `reputation_edge`. The reputation-aware buyer wins; a `high` band yields no edge.

- Information asymmetry (M6): scenarios gain an optional `seller_true_condition` — the item's hidden true quality routed only into the seller's private state (and a seller-side coach case), never visible to the buyer or a buyer-side coach. `product.condition` remains the public claim. Fully additive.

- Information asymmetry (M6): a buyer `inspect` tool (`opennego.tools.QualityInspectionTool`) returns a deterministic, *noisy* private estimate of the item's true quality on a `[0, 1]` axis; repeating it tightens the estimate at the cost of a turn. Backed by a new numeric `seller_true_quality` scenario field (seller-private, round-trips through `ScenarioArtifact`, seen by a seller-side coach only) and `opennego.quality.condition_to_quality`, which maps eBay-style condition claims to the same axis. The raw truth never crosses to the buyer.

- Information asymmetry (M6): `compute_match_score` is now quality-aware. On a deal the buyer's surplus is scored on the item's *realized* value (`buyer_budget * quality_ratio`), and the seller is penalized for the buyer overpaying relative to that realized value — an endogenous dispute/return exposure that spares honest or inspected fair deals. Threaded through the arena, market runtime, and serve scoring. Fully additive: with quality omitted or `true == claimed`, scores are identical to the previous headline-price model.

- Information asymmetry (M6): three quality-aware NPC archetypes (within legal bounds, distinct from the scam/safety archetypes) — `honest_discloser` (states the true condition and prices the defect in), `quality_overstater` (legal puffery, anchors high, never discloses; punished endogenously by the dispute penalty), and `quality_skeptic` (inspects when allowed and discounts willingness toward the estimated quality). Curated registry profiles added to `examples/data/npc_strategies.json` with provenance.

- Information asymmetry (M6): a `quality` skill drill (`opennego drill quality`, `opennego.skill_drill.v1`) — the lemon-market analogue of the M5 drills. It runs the same buyer twice against a conceding seller on a lemon, once inspecting-and-discounting and once at face value, scores both with the quality-aware match score, and reports the `elicitation_edge`. The inspecting buyer wins.

- Market runtime (M5): `opennego.market` builds a deterministic listings pool (`opennego.market_state.v1`) from product fixtures, advances it with a lifecycle step (age, price-drop on stale listings, expire/relist), and serves a discovery query of ranked listing cards.

- Market skill drills (M5): `opennego drill select` runs a deterministic listing-selection drill (`opennego.skill_drill.v1`) scored by attainable surplus relative to the optimum, where the cheapest sticker is a trap when the seller's reputation is low.

- Web client (M4): a React + Elastic UI frontend in `web/` (Vite,
  TypeScript) with agent definition (key write-only, read-only base
  prompt) and match replay. `opennego serve` serves the built
  `web/dist` when present, else a placeholder that explains the build.
  Built bundles stay out of git; CI verifies the build.
- Web client coach view: renders the v2 battle report (outcome,
  opponent read, weaknesses, decision points, safety), generates an
  evolved strategy candidate with its generalization verdict, and
  accepts (writing a lineage node) or rejects it; a train_only candidate
  is gated behind an explicit confirm.
- Web client ratings page and match rating ingestion: `opennego serve`
  matches are scored and recorded in a local rating store, and the
  Ratings tab shows buyer/seller tracks with uncertainty and match
  counts, highlighting the user's agent.

- Local web client backend (M4): `opennego serve` starts a stdlib
  `http.server` (zero new runtime deps) exposing JSON endpoints that
  wrap the existing API (profiles, agents, matches, trace, battle
  report, evolve, accept/reject with lineage, ratings). BYOK keys are
  write-only: never persisted to disk or returned by any endpoint.

- Rating layer (M3): per-match normalized-surplus score (`opennego.rating`) blending ZOPA split with market skill, non-deal and scam-safety handling per `docs/design/rating.md`, plus a SQLite `RatingStore` (`opennego.rating_store.v1`) with idempotent run-id ingestion and a continuous Bradley-Terry update on separate buyer and seller tracks with Glicko-style uncertainty.

- Coach layer (M2): `CoachPort` contract, `opennego.battle_report.v2`
  reports (decision points with counterfactuals, opponent read,
  phase-attributed weaknesses, safety verdicts) generated by the
  deterministic `RuleBasedCoach` from a visibility-filtered `CoachCase`.
  `learn`/`train`/`demo`/sparring now emit v2 battle reports; evolution and
  HTML reports accept v1 and v2. Scam-NPC engagement produces a critical
  safety attribution. New `opennego learn --coach` flag (rules default).
- BYOK `LLMCoach`: analyzes a visibility-filtered case through any
  `LLMPort`, parses strict v2 JSON with bounded retries, grounds every
  cited turn in the visible trace, and raises rather than silently
  downgrading. `opennego learn --coach llm --coach-model <id>`.
- Strategy candidates record coach provenance (coach kind, source report
  version, addressed phases and turns), and applying a candidate now
  rejects any attempt to overwrite the fixed base prompt.
- Held-out generalization for `opennego train --holdout-validation`: the
  opposite-role roster splits into train and held-out sets (scam
  archetypes in both), the patch is picked from the train set only, and
  the candidate is rerun across the roster. The training summary reports
  per-set score/deal-rate deltas and a verdict (improved/train_only/
  regressed); `apply-strategy` refuses a `train_only` candidate unless
  `--allow-train-only` is passed.
- Durable strategy lineage (`opennego.strategy_lineage.v1`): an
  append-only chain of applied strategy versions with parent links,
  source candidate/report, generalization verdict, and accept/reject
  decision. `apply-strategy --lineage <path>` appends a node; the new
  `opennego lineage` command prints and validates the chain (broken
  parent links or missing config artifacts fail validation).

- Market-grounded scenario generator with BATNA structure
  (`opennego.batna.v1`): buyer budgets derive from next-best active listings
  plus switching friction, seller reservations from patience-discounted
  resale minus relist cost; each agent sees only its own outside option.
- Market time structure: steppable `NegotiationEnvironment.step()` API,
  optional `NegotiationRules` (offer expiry, per-side offer caps, turn delay
  costs), and a `ghost` action with the `ghosted` outcome.
- Scenario pack pipeline (`opennego scenarios build|validate`,
  `opennego.scenario_pack.v1`): validated market data in, runnable
  multi-category scenario libraries with fingerprinted provenance out.
- NPC population expanded 5 → 17 archetypes with difficulty tiers and
  field-evidence provenance notes, including firm-price, ghosting,
  deadline-pressure, precise-counter, and safety (scam) archetypes.
- Published marketplace fee schedules (`opennego.fee_schedule.v1`) with
  required provenance: eBay US tiered final value fees, PayPal Goods and
  Services, local cash pickup; configs reference schedules via
  `transaction.schedule`.
- Active listings surface: `active_listing_search` tool, eBay Browse API
  adapter behind source-policy gates (`ingest-ebay-active`), and
  `validate-market --active-listings-file`.

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
