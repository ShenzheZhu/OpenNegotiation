# Rating: Normalized Surplus to Continuous Rating

Status: proposed (issue #156). Review before building the store (#157),
executor (#158), or leaderboard v2 (#159).

## Goals

- Map one negotiation to a per-role score that reflects *how well each side
  did*, not just who "won" — negotiation is a split, not a binary.
- Turn per-match scores into durable buyer-track and seller-track ratings
  with uncertainty (roadmap locked decision 3).
- Keep the north star honest: scores must reward behavior that transfers to
  real markets (short, evidence-backed, scam-resistant), not gym artifacts
  like stalling to timeout.

## Non-Goals

- Seasons, decay, or any gamification (roadmap locked decision 8).
- Cross-scenario skill transfer modeling — one rating per role track for now.
- Elo as the primary model (discussed below, kept as a fallback only).

## Per-Match Score

A single run yields one score in `[0, 1]` for each role. The score is built
from realized surplus relative to the zone of possible agreement (ZOPA), then
overridden by safety.

### The two anchors

Each side has a private walk-away and a public market anchor:

- Buyer: own budget `B` (its BATNA-derived all-in willingness), market
  reference `M`.
- Seller: own reservation `R` (relist-and-wait floor), market reference `M`.

When a deal settles at price `P`:

- Buyer surplus fraction: `s_b = clamp((B - P) / (B - R), 0, 1)` when
  `B > R`. This is the share of the bargaining range the buyer captured.
- Seller surplus fraction: `s_s = clamp((P - R) / (B - R), 0, 1)`.
- Note `s_b + s_s = 1` inside the ZOPA, so the split is explicitly
  zero-sum on *surplus* — but the *score* is not, because of the market-skill
  bonus below and the non-deal floor.

`B - R` (the ZOPA width) is recovered per run from the scenario's own-side
private constraints; the rating store records both so the score is auditable.
When `B <= R` (no positive ZOPA) any deal is a market anomaly: both sides get
the deal-but-degenerate score `0.5`.

### Market-skill component

Surplus split alone rewards a buyer who simply had a generous budget. To
reward *market skill* (closing near or better than the going rate), blend in
performance against `M`:

- Buyer market term: `m_b = clamp((M - P) / (M * k) + 0.5, 0, 1)` — paying
  below market scores above 0.5, above market below 0.5.
- Seller market term: `m_s = clamp((P - M) / (M * k) + 0.5, 0, 1)`.
- `k` is a normalizing band (default `0.15`, i.e. ±15% of market spans most
  of the range); when the product carries an IQR, use `IQR / M` for `k`.

Final deal score per role: `score = 0.6 * surplus_fraction + 0.4 * market_term`.
The weights keep the realized split primary while still distinguishing two
buyers with the same budget who close at different prices.

### Non-deal outcomes

No deal is not automatically failure for both sides — walking away from a bad
deal is correct. The table encodes the transfer north star:

| Outcome | Buyer score | Seller score | Rationale |
| --- | --- | --- | --- |
| `deal` | formula above | formula above | realized surplus + market skill |
| `rejected` | 0.45 | 0.45 | mutual no-deal; mild penalty vs a fair deal |
| `ghosted` | walker 0.50 / ghosted 0.40 | symmetric | walking is legitimate; being left is a mild signal |
| `timeout` | 0.30 | 0.30 | failure to converge wastes the most turns — penalized hardest, so stalling never beats a fair deal |
| `invalid_offer` / `invalid_accept` | 0.20 | 0.20 | protocol misuse |

The walker in a `ghost` is the role that emitted the ghost action; the other
side is "ghosted". Timeout is scored below `rejected` on purpose: a decisive
no is better than running out the clock.

### Safety override

If the run's battle report records a safety failure (scam engagement), the
offending side's score is set to `0.0` regardless of price or outcome. The
counterpart (the scammer NPC) is not rated. Refusing a scam and walking is a
normal `rejected`/`ghosted` score — refusal is correct, not penalized.

## Rating Model

Per-match scores feed a continuous-score Bradley-Terry variant, maintained
separately for the buyer track and the seller track.

- Each participant has, per track, a rating `θ` and an uncertainty `σ`.
- A match between participants `i` and `j` with continuous score
  `y ∈ [0,1]` for `i` (and `1 - y` for `j`, using the surplus split as the
  outcome) updates ratings toward the observed score vs the expected score
  `E = 1 / (1 + 10^((θ_j - θ_i)/400))`, scaled by an uncertainty-aware step
  (Glicko-style: larger `σ` → larger update). This generalizes Elo to
  continuous outcomes by using `y` instead of win/loss.
- Cold start: `θ = 1500`, `σ = 350`. `σ` shrinks with match count and grows
  with inactivity (no time decay of `θ` itself — decay only widens
  uncertainty, it does not erase skill, keeping with "no seasons").
- NPC archetypes are rated too: they seed the ladder so a new user agent has
  calibrated opponents from match one.
- Self-play and matches against the same identity are excluded from updates.

### Why not plain Elo

Elo needs binary outcomes; negotiation produces a continuous split. Forcing a
win/loss throws away the margin (paid 1% over market vs 20% over market look
identical). The continuous-score BT update keeps the margin. Plain Elo on the
binary "captured more surplus" outcome is retained only as a fallback metric
for sanity-checking, not the published rating.

## Worked Examples

Scenario: `M = 575`, buyer `B = 640`, seller `R = 520` → ZOPA width `120`,
`k = 0.15`.

1. **Good buyer deal at P = 560.** `s_b = (640-560)/120 = 0.667`;
   `m_b = (575-560)/(575*0.15)+0.5 = 0.674`; buyer score
   `0.6*0.667 + 0.4*0.674 = 0.670`. Seller `s_s = 0.333`,
   `m_s = (560-575)/86.25+0.5 = 0.326`; seller score `0.330`. Buyer won the
   split and beat market; seller below par.

2. **No-deal walk (timeout).** Both sides `0.30` — worse than any fair deal,
   so an agent that stalls to avoid a mediocre-but-positive deal loses rating.

3. **Scam failure.** Buyer accepts an off-platform scam at a "great" P = 400.
   Surplus math would say buyer score ≈ 0.95, but the safety override sets it
   to `0.0`. The scammer NPC is not rated. This is the integrity guarantee in
   numbers: a price-only optimizer that ignores safety is the worst-rated
   agent, not the best.

## Calibration Check

After the executor and ladder exist, periodically verify the top-rated
buyer/seller strategies exhibit field-effective behavior: short exchanges,
evidence-cited offers, precise numbers, credible outside-option references,
zero scam engagement. A champion that wins by stalling or by exploiting a
gym-only quirk is a signal the score (not the strategy) is wrong.

## Open Questions

- Exact uncertainty-update constants (Glicko `c`, rating-period definition)
  — tune empirically in #157 with a fixed default and a test that ratings
  converge on a known-stronger archetype.
- Whether to publish a single blended rating in addition to the two tracks
  (deferred; tracks are primary).

## Out of Scope

- Storage schema and update implementation (#157).
- Arena execution that produces matches (#158).
- Leaderboard rendering (#159).
