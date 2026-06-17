# Product Roadmap

OpenNegotiation is a training gym for marketplace agents. Users — buyers or
sellers — bring their own agent (any model through LiteLLM plus their own
strategy prompt), train it against calibrated opponents, get diagnosed by an
LLM coach, evolve the strategy prompt with evidence, and validate the result
in a realistic market sandbox built from real eBay data.

This document is the single source of truth for product direction. It records
the thesis, the locked design decisions, and the milestone plan. Engineering
process rules live in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Product Thesis: Market Skills, Decomposed

Operating in a real C2C market decomposes into trainable skills. Each skill
gets a controlled, reproducible training drill in the gym; the market sandbox
is the integrated exam, not the first encounter.

| Skill | Trained in | Scored by |
| --- | --- | --- |
| Listing selection (which deal is worth pursuing) | fixture drill, no opponent | ground-truth attainable surplus |
| Single-thread negotiation | duel mode vs NPC archetypes | normalized surplus |
| Walk-away timing | drill vs unwinnable NPCs | loss-cutting speed vs sunk cost |
| Multi-thread coordination | drill vs 2-3 concurrent scripted sellers | cross-thread leverage, no state confusion |
| Scam resistance | drill vs scammer archetypes | refusal correctness |
| Pricing and listing strategy (seller) | market sandbox episodes | time-to-sale vs realized price |
| Buyer triage (seller) | drill vs mixed-intent buyer NPCs | attention allocation vs realized surplus |

Two principles keep this honest:

1. **Capability comes from the harness, strategy comes from the prompt.** The
   runtime provides structured observations (normalized listing cards,
   comps-derived value deltas, a thread dashboard for concurrent
   negotiations). The agent makes decisions; it never freestyles bookkeeping.
2. **No weight training.** Improvement happens in the user-editable strategy
   prompt layer, on top of a fixed base protocol prompt. This is a deliberate
   product bet: in the harness era, negotiation outcomes hinge on strategy
   quality, not marginal model deltas.

## Two-Layer Architecture

```text
Market sandbox (realism layer)
  listings pool from real eBay data · search and discovery
  N buyers x M sellers · concurrent threads · clearing
  each buyer-seller thread is one duel-mode environment instance
        ^ calibrates BATNA parameters   v validates evolved strategies
Duel lab (training layer)
  controlled 1v1 negotiation · seeded and reproducible
  battle reports · prompt evolution · ratings
```

The layers feed each other:

- BATNA parameters injected into lab scenarios are calibrated from market
  (and real-data) distributions, not invented constants.
- Strategies evolved in the lab must hold up in the market sandbox — that is
  the transfer test.
- The sandbox itself is graded against reality: its clearing prices, deal
  rates, time-to-sale, and round counts must statistically match real eBay
  sold data. Real data is not just input; it is the calibration target.

## Realism Model

Gap analysis between textbook bilateral bargaining and real C2C markets,
ordered by impact. M1 closes the structural gaps inside the single-issue
protocol; M5 closes the market-level gaps; M6 closes the hidden-condition
information-asymmetry (lemon-market) gap; M7 closes the public-reputation gap.

| Gap | Reality | Fix |
| --- | --- | --- |
| Outside options (BATNA) | Leverage comes from competing listings and competing buyers, not from given constants | scenario generator derives private constraints from next-best alternatives (M1) |
| Time structure | Most real bargaining ends in 2-3 rounds; offers expire and bind; silence is the common rejection | offer expiry, counter limits, turn costs, ghosting outcomes (M1) |
| Information surface | Active-listing spread, days-on-market, and reputation drive bargaining power | active listings tool, listing-age signals (M1); hidden condition asymmetry, an `inspect` tool, quality-aware scoring, and quality NPC archetypes (M6); public seller-reputation signal, reputation-aware scoring, and reputation NPC archetypes (M7) |
| Counterpart population | Humans split the difference, ignore lowballs, sell at firm prices, ghost, and sometimes scam | NPC population calibrated on CraigslistBargain dialogues and eBay best-offer field evidence (M1) |
| Settlement economics | Platform fees, payment fees, and marketplace tax are real published schedules | real fee schedule pack with provenance (M1) |
| Multi-issue deals | Price, shipping, bundles, and extras trade off | deferred to protocol v2 (post-M5) |

Key references: Backus, Blake, Larsen, Tadelis, *Sequential Bargaining in the
Field* (QJE 2020); He et al., CraigslistBargain dataset (EMNLP 2018).

**North star:** strategies that win in the gym should converge on behaviors
documented as effective in real markets (short exchanges, evidence-backed
offers, precise numbers, credible outside options, zero tolerance for scam
patterns). If the gym's champion strategy is something that cannot exist in a
real market, the gym is wrong, not the strategy.

## Locked Design Decisions

1. Protocol v1 is single-issue (price). Multi-issue bargaining is protocol
   v2, a separate post-M5 track.
2. The coach is BYOK: it runs on the user's configured LiteLLM endpoint. A
   hosted coach is a future commercial option behind the same port.
3. Per-run score is normalized surplus; ratings use a continuous-score
   Bradley-Terry-style model with separate buyer and seller tracks.
4. The client ships first as a local web UI (`opennego serve`). The API is
   designed multi-tenant-ready for a later hosted arena.
5. The coach reads only the user-visible side of the trace. Opponent private
   state never enters battle reports — evolution must not be able to cheat.
6. Market population is deterministic-NPC-majority; LLM-backed agents are a
   bounded minority (cost control and liquidity).
7. Market autonomy is staged: L1 assigned listing, single thread; L2 agent
   picks from a runtime shortlist; L3 free selection with concurrent threads.
8. No gamification. No seasons, no lobby aesthetics. The rating is a
   capability measure; the sandbox is a validation instrument.
9. Every layer keeps a deterministic no-key path so CI exercises all
   contracts without credentials.

## Milestones

### M1 — Gym core realism

1. Scenario generator with BATNA structure: private constraints derived from
   next-best alternatives, seeded and reproducible.
2. Active listings tool (`active_listing_search`) with an official eBay
   Browse API adapter behind the existing source-policy gates.
3. Market time structure: offer expiry, counter limits, turn costs, ghosting
   outcomes, and a steppable environment API (`step()`) — the precondition
   for M5 concurrency.
4. Scenario library pipeline: `opennego scenarios build` turning ingestion
   outputs into multi-category scenario packs.
5. NPC population calibrated on real bargaining behavior, 10+ archetypes
   with difficulty tiers, including firm-price, ghosting, and scammer types.
6. Real marketplace fee schedules replacing fixture numbers, with provenance.

### M2 — Coach and prompt evolution

CoachPort contract and structured battle-report schema (decision points,
counterfactuals, opponent read, per-phase attribution) with the deterministic
rule layer as no-key fallback; LiteLLM coach adapter; prompt candidate
generation into the existing fixed-base/editable-strategy config contract;
held-out NPC validation against overfitting; evolution lineage tracking.

### M3 — Rating arena

Rating design doc first (surplus-to-score mapping, no-deal and timeout
handling), then persistent match/rating store, arena executor for reciprocal
schedules, leaderboard with ratings and uncertainty.

### M4 — Local web client

`opennego serve`: agent definition (model endpoint, local-only keys, strategy
prompt editor with read-only base prompt), match replay, battle report view,
one-click evolution accept/reject, ratings page. A plain market observation
page lands here once M5 exists.

### M5 — Market skills and market sandbox

Skill drills first (listing selection, walk-away, multi-thread coordination),
then the market runtime (listings pool and lifecycle, search/discovery,
concurrency scheduler, thread dashboard, clearing), then staged autonomy
L1 to L3, closing with the realism calibration report (sandbox distributions vs
real eBay distributions).

### M6 — Information asymmetry

The lemon-market gap, inside the single-issue protocol. Design doc first, then:
a hidden `seller_true_condition` routed only to the seller; a numeric
`seller_true_quality` axis with a buyer `inspect` tool returning a noisy
private estimate; quality-aware match scoring (the buyer's realized value falls
with hidden quality, the seller carries the dispute exposure of a buyer who
overpaid); `honest_discloser` / `quality_overstater` / `quality_skeptic` NPC
archetypes; and a quality-elicitation skill drill. Does not touch protocol v2.

### M7 — Reputation visibility

The public half of the information-asymmetry gap. A public `seller_reputation`
on the scenario (visible to both roles, not elicited), a shared
`opennego.reputation` band→risk map (consolidating the M5 selection-drill
weights), reputation-aware scoring that haircuts the same realized value the M6
quality score uses, `reputation_premium_seller` / `reputation_discount_buyer`
NPC archetypes, and a reputation skill drill. Fixtures by default with the live
eBay band behind the existing source gates. Does not touch protocol v2.

### M8 — Training season

Deepens the single-shot training loop into the "training factory" experience:
spar the whole roster, aggregate the coach's findings into a ranked weakness
profile, then generate and **held-out-validate** a candidate per top weakness
and return a ranked slate with an advisory recommendation (overfit demoted).
Nothing is auto-applied. `opennego train-season` + a static season report.

## Design Docs

Milestone work that needs review-before-build records the decision under
`docs/design/`:

- [Coach contract and battle report v2](design/coach.md) (M2)
- [Rating: normalized surplus to continuous rating](design/rating.md) (M3)
- [Local web client: `opennego serve`](design/serve.md) (M4)
- [Market skills and sandbox](design/market.md) (M5)
- [Information asymmetry: condition and reputation](design/information_asymmetry.md) (M6, M7)
- [Training season: aggregated weaknesses and a ranked candidate slate](design/training_season.md) (M8)

## Engineering Process

Work follows the issue-per-unit discipline: one integration train per
milestone (`integration/m<N>-<theme>`), `feat/issue-<N>-<slug>` branches,
checkpoint review every three closed issues, schema version bumps with
changelog entries for any artifact change.
