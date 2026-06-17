# Web Client Round-out: Surfacing M5–M9 in the Browser

Status: **accepted — milestone M10, in progress.** The engine shipped M1–M9 but
the browser client (`opennego serve` + the EUI app) still stops at the M4
feature set: define agent → match → coach report → evolve → ratings. Everything
since — the training season (M8), co-evolution (M9), and the hidden
condition/reputation signals (M6/M7) — is CLI-only. This milestone closes that
gap so a non-CLI user can reach the product's headline capabilities.

## Why

The client is the commercial-landing surface; nobody adopts a 30-command CLI.
The engine is already deep, so the highest-leverage work is making what exists
*reachable in the browser*, not adding more engine. Concretely the client is
missing the "training factory" experience (run a season, see where the agent
loses, pick a validated fix) and the self-play view (watch populations evolve),
plus the realism signals that make a match legible (was this a lemon? a
low-reputation seller?).

## Approach and verification boundary

- **API first, dispatch-tested.** Each feature is a new route on the stdlib
  `serve` backend whose handler is a pure function over `dispatch(...)` — fully
  no-key testable, like the existing routes. This is the solid, CI-verified
  deliverable.
- **EUI views build in CI.** New `.tsx` views are added to the existing app and
  must pass the `web-client` job (`npm ci && npm run build`). That proves they
  typecheck and bundle. **Visual correctness is not CI-verifiable here** and is
  explicitly the maintainer's local check (`opennego serve`).
- BYOK keys stay write-only at the boundary, exactly as today. The season and
  co-evolution runs are deterministic no-key by default.

## Scope

1. **Training season (M8) in the client.** `POST /api/train-season` →
   `run_training_season` for a stored agent's role; returns the weakness
   profile + ranked validated slate + recommendation. A `TrainingSeasonView`
   renders the ranked weaknesses and the candidate slate, and lets the user
   apply a chosen candidate through the existing strategy-config path (nothing
   auto-applied).
2. **Co-evolution (M9) in the client.** `POST /api/coevolve` → `run_coevolution`;
   returns per-generation leaderboards, champion genomes + lineage, and the
   fitness trajectory. A `CoevolutionView` renders the generational table and
   champion lineage.
3. **Condition & reputation (M6/M7) made legible.** Surface the public
   reputation band on the match/report views, the realized quality outcome
   post-match, and the buyer `inspect` results already present in the trace.
   Plus navigation wiring for the new views and README/roadmap updates.

Out: visual/design polish beyond functional rendering (maintainer's eye), the
hosted multi-tenant arena, protocol v2, and the BYOK prompt-evolution
implementation (separate, key-gated).

## Issues

1. Season API endpoint + `TrainingSeasonView`.
2. Co-evolution API endpoint + `CoevolutionView`.
3. Condition/reputation surfacing + navigation + docs.

Design-doc-first, integration-train discipline as M1–M9.
