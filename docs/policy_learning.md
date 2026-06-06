# Policy Learning And Strategy Marketplace

OpenNegotiation has three connected product layers:

1. Benchmark: measure negotiation and transaction performance under realistic
   market, tool, and settlement conditions.
2. Training / prompt optimization: explain why a user agent won, failed,
   overpaid, undersold, stalled, misused tools, or ignored transaction risk.
3. Strategy marketplace: provide curated NPC agents and strategy modules that
   users can spar against and learn from.

The first policy-learning slice is intentionally deterministic and no-key. It
can be run as a one-command MVP demo, or pointed at existing benchmark
artifacts to produce a battle report that can guide strategy prompt edits
without calling a live model provider.

## Base Versus Strategy

OpenNegotiation separates prompt and policy state into two layers.

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

Users can export their own improved strategy candidates into the same local
marketplace format:

```bash
opennego marketplace-export \
  --candidate /tmp/opennego-real-market-demo/strategy_candidate.json \
  --output /tmp/opennego-real-market-demo/marketplace_profile.json \
  --profile-id shared_buyer_guard_v1 \
  --name "Shared Buyer Guard" \
  --install-registry /tmp/opennego-local-marketplace.json
opennego validate-marketplace \
  --registry /tmp/opennego-local-marketplace.json \
  --profile /tmp/opennego-real-market-demo/marketplace_profile.json
```

The exported profile uses schema version
`opennego.strategy_marketplace_profile.v1`, but its top-level fields are also
compatible with `StrategyProfile`. Shared profiles carry
`opennego.strategy_config.v1` metadata that marks the sandbox `base_prompt` as
fixed and the `strategy_prompt` as the editable strategy layer. Installing the
profile writes or updates a local `opennego.policy_learning.v1` registry, so
existing commands can list it:

```bash
opennego strategies --registry /tmp/opennego-local-marketplace.json --role buyer
```

Duplicate profile ids are rejected by default. Pass `--overwrite` only when
intentionally replacing a local shared strategy profile. The validation command
returns `opennego.strategy_marketplace_validation.v1` JSON and exits nonzero
when profile versioning, prompt-layer metadata, registry schema, or duplicate
ids are malformed.

## Strategy Sparring Suite

`opennego spar` turns marketplace profiles into a repeatable training suite.
The default path is no-key:

```bash
opennego spar \
  --output-dir /tmp/opennego-sparring \
  --report /tmp/opennego-sparring.html \
  --opponent-profile seller_hardline_anchor_v1 \
  --opponent-profile seller_hidden_fees_v1
```

The command writes `sparring_suite.json` at the output root and one
`battle_report.json` under each selected profile directory. When `--report` is
provided, it also renders a compact static HTML summary for demos and review.
Its current execution mode is `profile_backed_fixture_sparring`: deterministic
local user agents spar against deterministic counterparties instantiated from
the selected NPC profiles. The selected profile drives the counterparty actor,
benchmark trace, battle-report opponent archetype, expected traps, failure
modes, and strategy patch. This is not yet a hosted marketplace, but it gives
users a reproducible curriculum surface for prompt optimization.

If no `--opponent-profile` is provided, the command selects every registry
profile with the opposite role from `--user-role`. A buyer-owned user agent
therefore spars against seller profiles by default.

Python API users can spar a custom `AgentPort` implementation against the same
NPC profiles:

```python
from opennego.sparring import run_sparring_suite

summary = run_sparring_suite(
    output_dir="/tmp/my-agent-sparring",
    user_role="buyer",
    opponent_profile_ids=("seller_hardline_anchor_v1",),
    user_agent_factory=my_buyer_factory,
    user_agent_kind="my_buyer",
)
```

For arbitrary custom factories, the custom factory path and `--user-strategy`
path are mutually exclusive unless the caller explicitly wires a factory that
consumes the strategy candidate. Both paths use the same environment loop,
traces, metrics, battle reports, and sparring summary contracts.

The profile counterparty can also be swapped from deterministic profile-backed
logic to a provider-backed profile agent through the CLI:

```bash
OPENROUTER_API_KEY=... opennego spar \
  --output-dir /tmp/my-agent-live-npc-sparring \
  --opponent-profile seller_hardline_anchor_v1 \
  --opponent-llm-model openrouter/openai/gpt-4o-mini \
  --opponent-llm-max-tokens 256
```

`--opponent-llm-model` requires at least one explicit `--opponent-profile` to
bound live provider calls. Python API callers can wire the same path directly:

```python
summary = run_sparring_suite(
    output_dir="/tmp/my-agent-live-npc-sparring",
    user_role="buyer",
    opponent_profile_ids=("seller_hardline_anchor_v1",),
    user_agent_factory=my_buyer_factory,
    user_agent_kind="my_buyer",
    opponent_agent_factory=my_profile_llm_factory,
    opponent_agent_kind="llm_profile_seller",
)
```

This still uses the same artifacts and learning reports. Live provider calls
remain optional and are not required for no-key CI.

For live LLM user agents, the CLI can also instantiate the user policy directly
through LiteLLM. This is the recommended live-provider path when you want to
test the strategy-evolution loop without writing a local Python factory:

```bash
OPENROUTER_API_KEY=... opennego spar \
  --output-dir /tmp/my-live-user-sparring \
  --opponent-profile seller_hardline_anchor_v1 \
  --user-llm-model openrouter/openai/gpt-4.1-nano \
  --user-llm-max-tokens 220 \
  --opponent-llm-model openrouter/openai/gpt-4.1-mini \
  --opponent-llm-max-tokens 220 \
  --learning-tool-regime buyer_private_market_search \
  --no-fail-fast
```

`--user-llm-model` also requires at least one explicit `--opponent-profile` to
bound live provider calls. When it is combined with `--user-strategy`, the
strategy candidate is injected into the live user agent as additional strategy
instructions while the base action schema and environment rules remain fixed.

## Battle Report Schema

The quickest end-to-end path is:

```bash
opennego mvp-demo --output-dir /tmp/opennego-mvp-demo --report /tmp/opennego-mvp-demo.html
opennego validate-demo-bundle --manifest /tmp/opennego-mvp-demo/mvp_demo_manifest.json
```

This runs the small real-market benchmark, writes
`/tmp/opennego-mvp-demo/leaderboard_summary.json` plus
`/tmp/opennego-mvp-demo/battle_report.json`, writes an
`opennego.mvp_demo_bundle.v1` handoff manifest at
`/tmp/opennego-mvp-demo/mvp_demo_manifest.json`, and renders an HTML page with
the leaderboard preview, Training / Prompt Optimization section, and Strategy
Marketplace section. The leaderboard preview is rendered from the versioned
leaderboard summary artifact when it is available. The validation command emits
`opennego.mvp_demo_bundle_validation.v1` JSON and is the no-key release check
that the benchmark, learning report, strategy candidate, and HTML report still
line up as one coherent demo bundle.

For a focused no-key training loop:

```bash
opennego train \
  --output-dir /tmp/opennego-training \
  --opponent-profile seller_hardline_anchor_v1 \
  --parent-strategy-id buyer_baseline
```

`opennego train` writes `opennego.training_loop.v1` JSON at
`/tmp/opennego-training/training_loop.json`. It runs baseline sparring, selects
the lowest-scoring completed battle report, writes a strategy candidate, reruns
the same NPC profile with that candidate, and compares the before/after battle
reports. The summary records the shared `opennego.sparring.run_sparring_suite`
runtime so the loop remains artifact-backed instead of becoming a separate
prompt-only simulator.

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
  --output /tmp/opennego-real-market-demo/battle_report.json \
  --user-role buyer \
  --opponent-profile seller_hardline_anchor_v1
opennego report --input-dir /tmp/opennego-real-market-demo --output /tmp/opennego-mvp-demo.html
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

## Strategy Evolution Artifacts

`opennego evolve` turns a battle report into a versioned strategy candidate:

```bash
opennego evolve \
  --battle-report /tmp/opennego-real-market-demo/battle_report.json \
  --output /tmp/opennego-real-market-demo/strategy_candidate.json \
  --parent-strategy-id buyer_baseline \
  --iteration 1
```

The candidate artifact uses schema version `opennego.strategy_evolution.v1` and
records:

- `candidate_id`, `parent_strategy_id`, and `iteration`
- user role, source run id, scenario id, and opponent profile id
- strategy prompt patch text
- applied lesson ids and patch snippets
- expected improvements derived from trace-grounded recommendations
- a recommended rerun command and comparison command

`opennego apply-strategy` applies that candidate into a reusable strategy
configuration artifact:

```bash
opennego apply-strategy \
  --candidate /tmp/opennego-real-market-demo/strategy_candidate.json \
  --output /tmp/opennego-real-market-demo/strategy_config.json \
  --strategy-id buyer_baseline_v1
```

The config artifact uses schema version `opennego.strategy_config.v1`. It keeps
the base sandbox prompt fixed, stores the editable strategy prompt, records the
prompt-layer contract, and preserves candidate lineage, applied lesson ids,
patch snippets, source run id, source battle report, and expected improvements.
External user agents can consume this config without OpenNegotiation mutating their
source code.

External teams can also package the config into a validated adapter artifact:

```bash
opennego export-training-adapter \
  --strategy-config /tmp/opennego-real-market-demo/strategy_config.json \
  --output /tmp/opennego-real-market-demo/external_training_adapter.json \
  --agent-kind team_buyer_agent
opennego validate-training-adapter \
  --adapter /tmp/opennego-real-market-demo/external_training_adapter.json
```

The adapter uses schema `opennego.external_training_adapter.v1`. It tells an
external user agent to load `base_prompt` as the read-only sandbox layer and
`strategy_prompt` as the editable policy layer. It deliberately sets
`code_mutation: false`; OpenNegotiation does not rewrite arbitrary external
agent code.

The deterministic sparring runtime can consume the candidate directly:

```bash
opennego spar \
  --user-role buyer \
  --opponent-profile seller_hardline_anchor_v1 \
  --user-strategy /tmp/opennego-real-market-demo/strategy_candidate.json \
  --output-dir /tmp/opennego-rerun
```

For the no-key MVP, the candidate is applied as deterministic policy knobs for
the user agent. Buyer candidates can tighten market-reference price discipline
and seller candidates can tighten reservation or market-floor behavior. The
sparring summary and per-run manifests record the candidate id, parent strategy
id, source run id, and applied lesson ids so before/after runs remain
auditable.

For live LLM user agents, the same candidate can be supplied to the rerun:

```bash
OPENROUTER_API_KEY=... opennego spar \
  --output-dir /tmp/opennego-live-rerun \
  --opponent-profile seller_hardline_anchor_v1 \
  --user-strategy /tmp/opennego-real-market-demo/strategy_candidate.json \
  --user-llm-model openrouter/openai/gpt-4.1-nano \
  --opponent-llm-model openrouter/openai/gpt-4.1-mini \
  --learning-tool-regime buyer_private_market_search \
  --no-fail-fast
```

The rerun manifest records the same `user_strategy` metadata as deterministic
candidate-backed sparring, and the live user agent receives the candidate's
strategy prompt plus applied lessons as additional system instructions.

After the user reruns their agent with the candidate strategy, `opennego compare`
can compare the before/after battle reports:

```bash
opennego compare \
  --before /tmp/opennego-real-market-demo/battle_report.json \
  --after /tmp/opennego-rerun/battle_report.json \
  --output /tmp/opennego-rerun/strategy_comparison.json
```

The comparison artifact uses schema version `opennego.strategy_comparison.v1`
and reports score delta, outcome change, buyer/seller price movement, resolved
failure modes, new failure modes, resolved lesson ids, and new lesson ids. This
keeps the prompt-optimization loop auditable without automatically editing user
agent code.

When `battle_report.json` is present in the benchmark output root, the static
HTML report renders a Training / Prompt Optimization section. The same report
also renders `leaderboard_summary.json` participant coverage when available and
loads the local NPC strategy marketplace from `examples/data/npc_strategies.json`.

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
- versioned strategy candidate, applied strategy config, and comparison
  artifacts
- CLI commands for listing profiles, writing battle reports, and rendering the
  one-command MVP demo with visual, machine-readable, and bundle-manifest
  artifacts
- no-key sparring suite artifacts for selected marketplace profiles
- no-key runtime application of versioned strategy candidates in sparring
- one-command no-key training loop for sparring, strategy extraction, rerun,
  applied strategy config, and comparison artifacts
- local export and installation of strategy candidates as marketplace profiles

Out of scope:

- model fine-tuning
- automatic edits to user agent code
- provider-backed summarization
- hosted marketplace backend
- large NPC library
- profile-backed live model opponent execution

The near-term product loop is:

1. User runs an agent in the benchmark.
2. OpenNegotiation scores the run.
3. OpenNegotiation generates a battle report.
4. OpenNegotiation converts the battle report into a strategy candidate.
5. OpenNegotiation applies the candidate into a versioned `strategy_config.json`.
6. User consumes that config in their own agent integration, or reruns the
   no-key local candidate through `opennego spar --user-strategy`.
7. User reruns against the same or harder NPC profile.
8. OpenNegotiation compares the before/after battle reports.

`opennego train` automates steps 3-8 for the no-key local strategy-candidate
runtime and writes `strategy_config.json` next to the candidate.
