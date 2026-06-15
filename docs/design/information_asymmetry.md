# Information Asymmetry: Condition and Reputation (Proposal)

Status: **proposal, awaiting maintainer go/no-go.** Not started. This is
post-roadmap scope flagged in the realism model (the "lemon market" gap). It
extends the single-issue price protocol — it does **not** introduce multi-issue
bargaining (that remains the separate protocol-v2 track).

## Why

Today both sides see the same `condition` string and the same market
reference. Real C2C markets run on *asymmetric* information:

- The seller knows the item's true condition; the buyer infers it from photos,
  the description, and questions (the classic lemon-market problem).
- Reputation is a public but noisy signal: a high-feedback seller is a safer
  bet at the same price; a low-feedback seller carries risk the buyer must
  price in.

Without this, the gym cannot train two real skills: a buyer **eliciting and
discounting for hidden quality**, and a seller **credibly signaling quality**.
It is the highest-value realism gap left after M1–M5.

## Scope

In (single-issue, price-only):

- A hidden `true_condition` on the scenario, visible only to the seller's
  private state; the buyer sees a public `condition_claim` plus noisy signals
  (photo quality, description specificity, seller reputation band).
- A buyer `inspect` / `ask` tool that returns a noisy quality estimate
  (private to the buyer), so eliciting information costs a turn but reduces
  uncertainty — gated by the existing tool-regime and visibility machinery.
- Settlement and scoring account for realized quality: a buyer who overpays
  for a misrepresented item realizes negative surplus (return/dispute risk
  already modeled in the transaction simulator); a seller who misrepresents
  faces a reputation/dispute penalty.
- New deterministic NPC archetypes: `honest_discloser`, `quality_overstater`
  (within legal bounds — distinct from the existing safety/scam archetypes),
  and a buyer `quality_skeptic`.

Out (deliberately):

- Multi-issue bargaining (protocol v2).
- Outright fraud beyond the existing scam-safety archetypes.
- Hosted/multiplayer concerns.

## Sketch

- `schema`: add optional `true_condition` and `condition_claim` to the product
  / scenario; the environment routes `true_condition` only into the seller's
  private state, mirroring how budgets/reservations are already kept private.
  The coach's visibility red line extends automatically — the buyer-side coach
  never sees `true_condition`.
- `tools`: an `inspect` ToolPort returning a noisy estimate of true condition,
  private to the caller; deterministic given seed.
- `metrics`/`rating`: a realized-quality term so the normalized-surplus score
  reflects buying a lemon, not just the headline price.
- A new realism drill: "quality elicitation" — the buyer that inspects and
  discounts beats the one that takes the claim at face value, analogous to the
  existing skill drills.

## Open questions for the maintainer

1. Go/no-go: is this the next milestone (M6), or deferred behind protocol v2 /
   the hosted arena?
2. Reputation source: synthesize a `feedback_score` into fixtures, or pull a
   (non-PII) seller reputation band from the eBay Browse adapter under the
   existing source-policy gates?
3. How hard should misrepresentation bite — a soft surplus discount, or a
   hard dispute-failure path through the transaction simulator?

## Why this is only a proposal

This document exists so the direction is reviewable before any code. Nothing
is implemented; opening or closing this PR is the go/no-go. If accepted it
becomes milestone M6 with issues per component, following the same
design-doc-first, integration-train discipline as M1–M5.
