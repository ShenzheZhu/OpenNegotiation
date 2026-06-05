# Policy Learning And Strategy Marketplace

OpenNego has three connected product layers:

1. Benchmark: measure negotiation and transaction performance under realistic
   market, tool, and settlement conditions.
2. Training / prompt optimization: explain why a user agent won, failed,
   overpaid, undersold, stalled, misused tools, or ignored transaction risk.
3. Strategy marketplace: provide curated NPC agents and strategy modules that
   users can spar against and learn from.

The first policy-learning slice is intentionally deterministic and no-key. It
reads existing benchmark artifacts and produces a battle report that can guide
strategy prompt edits without calling a live model provider.

## Base Versus Strategy

OpenNego separates prompt and policy state into two layers.

`Base` is fixed by the sandbox:

- role and protocol rules
- structured action schema
- tool permissions and visibility
- transaction simulator constraints
- invariant checks such as budget, reservation, and settlement semantics

Users cannot edit this layer. Keeping it fixed makes benchmark runs comparable
and prevents user strategy edits from mutating the evaluation protocol.

`Strategy` is editable by the user:

- negotiation style
- concession policy
- risk tolerance
- disclosure behavior
- opponent-modeling heuristics
- tool-use timing and fallback policy

The policy-learning module only recommends edits to the strategy layer. It does
not patch the base prompt or the environment rules.

## NPC Strategy Registry

Preset NPC agents are represented as strategy profiles in
`examples/data/npc_strategies.json`.

Each profile includes:

- `id`: stable identifier, for example `seller_hardline_anchor_v1`
- `role`: `buyer` or `seller`
- `archetype`: compact behavior family
- `difficulty`: coarse curriculum level
- `base_prompt`: fixed protocol instructions for that NPC
- `strategy_prompt`: editable tactical behavior
- `expected_traps`: what this NPC is designed to test
- `allowed_tools`: tools the profile may use
- `tags`: discovery labels for marketplace filtering

List marketplace profiles with:

```bash
opennego strategies
opennego strategies --role seller
```

This is a local curated marketplace in the MVP. A hosted marketplace or
contributed strategy backend is intentionally out of scope for the first slice.

## Battle Report Schema

`opennego learn` reads one completed benchmark run directory:

```text
run_dir/
  manifest.json
  scenario.json
  trace.jsonl
  metrics.json
```

It writes a policy-learning report:

```bash
opennego run --config configs/real_market_demo.yaml --output-dir /tmp/opennego-real-market-demo
opennego learn \
  --input-dir /tmp/opennego-real-market-demo/real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13 \
  --output /tmp/opennego-battle-report.json \
  --user-role buyer \
  --opponent-profile seller_hardline_anchor_v1
```

The JSON report uses schema version `opennego.policy_learning.v1` and contains:

- run id and scenario id
- user role
- opponent profile id
- outcome and deal price
- policy score
- natural-language battle summary
- failure mode categories
- strengths
- trace-grounded lessons
- suggested strategy prompt patch
- paths to the source benchmark artifacts

Lessons cite trace events through `event_index`, `turn`, `role`, `action_type`,
and a short event summary. This keeps policy learning tied to benchmark
evidence instead of creating a disconnected logging format.

Example lesson excerpt from the no-key real-market demo:

```json
{
  "id": "buyer_overpaid_market",
  "category": "price_discipline",
  "severity": "high",
  "finding": "The accepted price $608.00 is more than 5% above the market reference $575.00.",
  "suggested_strategy_patch": "Never exceed market_reference * 1.05 unless a written exception is justified by condition, bundle value, or time preference.",
  "evidence": [
    {
      "event_index": 0,
      "turn": 1,
      "role": "buyer",
      "action_type": "offer"
    },
    {
      "event_index": 1,
      "turn": 2,
      "role": "seller",
      "action_type": "accept"
    }
  ]
}
```

## Deterministic Lesson Heuristics

The MVP extracts a small set of high-signal lessons:

- no-deal recovery when a run rejects or times out
- missed market-tool use when tools are available but unused
- buyer overpayment relative to market reference
- seller underselling below reservation or market reference
- transaction-risk blind spots after a deal
- tool-failure fallback behavior
- opponent trap awareness from NPC profiles

These are not intended to replace model-generated coaching. They are the stable,
no-key baseline that future LLM summarizers can build on.

## MVP Boundary

In scope:

- no-key NPC strategy registry
- no-key battle report generation from artifacts
- trace-grounded policy lessons
- strategy prompt patch suggestions
- CLI commands for listing profiles and writing reports

Out of scope:

- model fine-tuning
- automatic edits to user agent code
- provider-backed summarization
- hosted marketplace backend
- large NPC library

The near-term product loop is:

1. User runs an agent in the benchmark.
2. OpenNego scores the run.
3. OpenNego generates a battle report.
4. User edits only the strategy prompt.
5. User reruns against the same or harder NPC profile.
