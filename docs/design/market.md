# Market Skills and Sandbox

Status: proposed (issue #176). Review before building the drills (#177–#179),
the runtime (#180–#181), autonomy levels (#182), or calibration (#183).

## Goals

- Turn the 1v1 lab into a market: the user's agent operates among many buyers
  and sellers — finding listings, negotiating concurrent threads, and clearing
  deals — on real eBay-derived data.
- Decompose market competence into reproducible, scored skill drills so the
  market is an exam over trained skills, not an agent's first encounter (the
  "don't jump into the market and drown" principle).
- Reuse what exists: the steppable `NegotiationEnvironment`, the rating layer,
  the active-listing card shape, and scenario packs. The market adds a
  scheduler and a world, not a parallel negotiation engine.

## Non-Goals

- Hosted/multiplayer market (local, single-user, deterministic-first).
- Auto-tuning the sandbox to match reality (calibration reports the gap; it
  does not close it automatically).
- Gamification — seasons, lobbies, cosmetics (roadmap locked decision 8).

## Skill Drills

Each drill is a controlled, seed-reproducible, no-key scenario with a defined
score, mapping to the roadmap's market-skills table and the rating phases.

| Drill (#) | Skill | Setup | Score |
| --- | --- | --- | --- |
| listing selection (#177) | pick the deal worth pursuing | N fixture listing cards with known attainable surplus | selection's attainable surplus / optimum |
| walk-away (#178) | cut losses fast | unwinnable / firm-price NPCs | decisive walk beats timeout (rating non-deal table) |
| multi-thread (#179) | cross-thread leverage without state confusion | 2-3 concurrent counterpart threads via `step()` | leverage used + best close, penalize cross-thread leakage |

Drills emit versioned artifacts (`opennego.skill_drill.v1`) and feed the same
normalized-surplus scoring vocabulary as ratings, so drill performance and
match performance are comparable.

## Market Runtime

### MarketState and lifecycle (#180)

`MarketState` is built deterministically from scenario-pack / sold-comps
fixtures: a pool of listings, each with asking price, condition, listing age,
and a seller participant id. A lifecycle `step(seed)` advances the world:

- age every active listing by one period,
- drop price on listings stale beyond a threshold (toward sold-comps median),
- expire listings past a max age and relist a fraction at refreshed prices.

Snapshots serialize as `opennego.market_state.v1`. Discovery returns ranked
normalized listing cards (the same shape as `active_listing_search`), so
agents and the UI reuse one card format.

### Concurrency scheduler and clearing (#181)

The scheduler interleaves many `NegotiationEnvironment.step()` instances — one
per live buyer-seller thread — round-robin, so no thread blocks another. This
is exactly why `step()` was built in M1. Each participant has a thread
dashboard (per-thread latest offer, distance to its own constraint, remaining
time) in its observation.

Clearing: when a party accepts, the deal settles through the transaction
simulator and conflicting threads close — a sold listing's other buyer threads
end (`listing_taken`), and a committed buyer's other seller threads end
(`bought_elsewhere`). A seller weighing several live buyer offers picks the
best per its policy; a buyer commits to one seller.

Cost control (locked decision 6): the population is deterministic-NPC-majority.
The user's agent plus a bounded number of LLM agents are the only paid actors;
the rest are scored scripted archetypes that provide liquidity at zero cost.

A market episode serializes as `opennego.market_episode.v1` (threads,
clearings, per-participant outcomes) and its per-side scores ingest into the
rating store, idempotent by episode/thread id.

## Staged Autonomy (#182)

Autonomy is added in controlled steps; each level has its own metric and is
independently runnable:

- **L1** — assigned listing, single thread. A thin wrapper over a duel; the
  market chooses nothing.
- **L2** — the runtime presents a discovery shortlist; the agent selects one
  and negotiates a single thread.
- **L3** — the agent free-selects from discovery and negotiates concurrent
  threads through the full scheduler.

A user can see which level their agent is reliable at — itself a product
signal ("your agent is a solid L2; multi-thread needs work").

## Realism Calibration (#183)

The sandbox is only worth as much as it is realistic. `market calibrate`
compares sandbox-generated distributions against a reference (real eBay sold
data, or a fixture reference for no-key CI):

- clearing price vs sold-comps median/IQR,
- time-to-sale / negotiation round counts,
- deal rate.

Each metric gets a within-tolerance verdict and the report an overall status
(`opennego.market_calibration.v1`). This is the operational form of the
roadmap's transfer north star: if the sandbox's champion behavior or its
aggregate distributions diverge from real markets, the report makes the gap
visible. It reports the gap; it does not auto-close it.

## Schema Ids

New, all additive: `opennego.skill_drill.v1`, `opennego.market_state.v1`,
`opennego.market_episode.v1`, `opennego.market_calibration.v1`. Market
episode per-side scores reuse `opennego.rating` and the existing rating store.

## Test Plan

- Drills: determinism by seed; optimal action scores highest; wrong action
  scores lower.
- Runtime: lifecycle reproducibility; scheduler advances N×M threads
  deterministically; a clear closes conflicting threads; episode scores
  ingest idempotently.
- Autonomy: each of L1/L2/L3 runs no-key with its metric.
- Calibration: deterministic report over a fixed episode + fixture reference,
  with per-metric verdicts.

## Out of Scope

- Implementation lives in the issues above; this document is the contract.
