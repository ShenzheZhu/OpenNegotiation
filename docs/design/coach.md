# Coach Contract and Battle Report v2

Status: proposed (issue #142). Review this document before implementing the
schema skeletons.

## Goals

- One `CoachPort` interface that both the deterministic rule coach (no-key
  default) and the BYOK LLM coach implement, so every surface (`learn`,
  `train`, `demo`, the M4 client) consumes coaching through one contract.
- A battle report that explains *why* a negotiation went the way it did:
  decision points, counterfactuals, an opponent read, and weakness
  attribution by phase — not just rule-trigger lessons.
- A hard, testable visibility boundary: evolution must never be able to
  cheat off the counterpart's private state.

## Non-Goals

- Multi-candidate tournament search (post-M2).
- Cross-run aggregate coaching ("your last 20 runs show...") — single-run
  reports first; aggregation is a later layer over the same schema.
- Any platform-hosted coach. BYOK only (roadmap locked decision 2).

## CoachPort

```python
class CoachPort(Protocol):
    kind: str  # "rules" | "llm:<model>"

    def review(self, case: CoachCase) -> BattleReport: ...
```

`CoachCase` is the *filtered* view of one completed run:

| Field | Content | Source |
| --- | --- | --- |
| `user_role` | buyer or seller | caller |
| `scenario_public` | product, list price, market reference, max turns | scenario.json minus counterpart private constraints |
| `user_private` | the user's own budget/reservation, own BATNA block | scenario + metadata.batna (own side only) |
| `visible_trace` | events visible to the user role (own private tool calls included, counterpart's excluded) | trace.jsonl filtered |
| `metrics` | role-filtered metric report | metrics.json minus counterpart-derivable metrics |
| `rules` | active NegotiationRules, if any | manifest metadata |
| `opponent_card` | NPC public card: name, archetype, difficulty, summary, expected_traps, tags | registry profile (public fields only) |

### The visibility red line

The coach sees exactly what the user agent could have seen, plus the public
NPC card. Specifically excluded, enforced by the `CoachCase` builder and
covered by tests:

- counterpart reservation price / budget,
- derived metrics that reconstruct them (`buyer_budget_slack` for seller
  cases; `seller_profit_vs_reservation` and `normalized_deal_price` for
  buyer cases),
- counterpart's side of `metadata.batna`,
- counterpart private tool calls and results,
- NPC policy parameters (concession fractions, ghost thresholds) — only the
  registry's public card is visible.

Rationale: a coach that reads the opponent's reservation produces advice
that cannot transfer to real markets, and ratings built on such evolution
would be fraudulent. This rule is the product's integrity guarantee.

## Battle Report v2 (`opennego.battle_report.v2`)

```json
{
  "schema_version": "opennego.battle_report.v2",
  "run_id": "...",
  "user_role": "buyer",
  "coach": {"kind": "llm:openrouter/x", "report_generated_by": "coach"},
  "outcome_summary": {
    "outcome": "deal",
    "deal_price": 612.5,
    "surplus_assessment": "paid 6.5% over sold-comps median"
  },
  "opponent_read": {
    "observed_tactics": ["high anchor", "slow concessions"],
    "archetype_guess": "hardline_anchor",
    "confidence": "high"
  },
  "decision_points": [
    {
      "turn": 3,
      "phase": "negotiation",
      "situation": "seller cited a comp 12% above the median you had retrieved",
      "action_taken": "conceded to 640 without challenging the comp",
      "assessment": "missed_verification",
      "counterfactual": "citing your own retrieved median (575) supports holding near 590"
    }
  ],
  "weaknesses": [
    {
      "id": "buyer_overpaid_market",
      "phase": "negotiation",
      "severity": "major",
      "evidence_turns": [3, 5],
      "summary": "accepted above market reference without using retrieved evidence"
    }
  ],
  "lessons": [
    {"id": "buyer_overpaid_market", "patch": "Anchor counters on retrieved comps; never accept above the median without a stated reason."}
  ],
  "safety": {"violations": [], "passed": true}
}
```

Notes:

- `phase` taxonomy: `selection` (reserved until M5 drills), `negotiation`,
  `closing`, `safety`. Phases attribute *where* a weakness lives so prompt
  evolution can edit the matching strategy-prompt section.
- `lessons[].id` keeps the v1 lesson-id vocabulary where applicable, so
  `evolution.py` and existing comparison artifacts keep working unchanged.
- `safety.violations` is non-empty when the user agent agreed to a scam-NPC
  hook (off-platform payment, overpayment refund); severity is always
  `critical` and the lesson patches the safety section of the strategy
  prompt.
- The rule coach fills `decision_points` and `opponent_read` with
  deterministic, trace-derived entries (e.g. rule events from the time
  structure, accept-vs-reference checks); fields it cannot infer stay empty
  rather than fabricated. LLM coaches must ground every `evidence_turns`
  reference in real trace turns; ungrounded turns fail validation.

## Compatibility and migration

- v1 reports (`opennego.policy_learning.v1`) remain readable; `learn`
  gains `--report-version` defaulting to v2 once #143 lands. Demo bundle
  expected-schema pins bump in the same PR with a CHANGELOG entry.
- `write_strategy_candidate` consumes v2 via the `lessons` list — identical
  shape to v1 lessons.

## Test plan

- JSON round-trip and validation tests for the schema dataclasses.
- CoachCase builder red-line tests: serialized case contains no counterpart
  reservation/budget/batna/private-tool content for both roles.
- Rule-coach golden test: same run produces v1-equivalent lesson ids inside
  a valid v2 envelope.
- LLM-coach contract tests (fake gateway, #144): malformed output retried
  then surfaced; ungrounded evidence turns rejected.
