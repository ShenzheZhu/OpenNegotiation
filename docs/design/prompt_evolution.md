# BYOK Prompt Evolution: Evolving Strategy Prompts with a Real Model

Status: **accepted — milestone M11, in progress.** Makes the project's central
thesis real: *good prompts/strategy are the lever*, so evolve the natural-language
strategy prompt itself, with the user's own model. Until now every "evolution"
path has been rule-based (M2/M8), numeric-genome (M9), or just a seam (M9's
`agent_factory`). This wires a population of **prompts** through an LLM-driven
mutation operator and the existing tournament scoring.

## The hard constraint (stated up front)

The fitness of a *prompt* only moves when matches run through a real model — a
deterministic agent ignores prompts. So:

- **No-key (CI):** the loop, selection, lineage, and artifact are verified with
  a deterministic fake mutator and a fake prompt-sensitive agent factory. This
  proves the machinery — *that evolution selects higher-fitness prompts* — on a
  synthetic, prompt-derived fitness, without any credentials.
- **BYOK (real):** the same loop with a LiteLLM-backed mutator and LLM agents.
  This is where prompts actually improve against real opponents. It needs the
  user's key and is **not** exercised in CI. The CI fake and the BYOK real path
  share one code path; only the injected mutator and agent factory differ.

This boundary is the honest version of "make it real": the engine is real and
proven; the model quality is the user's to run.

## Model

- **PromptGenome**: `{id, prompt, parent_ids}` — a natural-language strategy
  prompt and its lineage.
- **`PromptMutatorPort`**: `mutate(prompt, feedback) -> str` and
  `crossover(a, b) -> str`.
  - `LLMPromptMutator(llm, model)` meta-prompts the model to improve a strategy
    prompt given its match feedback, or to combine two parents (BYOK).
  - `FakePromptMutator` applies deterministic, inspectable string transforms
    (CI, demos).
- **Agent factory**: `PromptGenome -> agent`.
  - BYOK: `make_profile_llm_agent(synthetic_profile(prompt), llm, model)` — an
    LLM agent whose system prompt embeds the evolved strategy prompt.
  - CI: a deterministic agent whose behavior reads a parameter the fake mutator
    tunes, so selection is observable no-key.
- **Loop (`run_prompt_evolution`)**: a population of prompts is evaluated each
  generation against a **fixed** opponent roster (the curated NPCs) on a seeded
  scenario set, scored with the existing quality/reputation-aware
  `compute_match_score`; fitness is the mean role-score. Elites survive; the
  rest are refilled by LLM mutation (seeded with the elite's match feedback) and
  crossover. With a fixed opponent roster, elite fitness is monotone — the
  no-key regression signal that the loop genuinely selects.
- **Artifact** `opennego.prompt_evolution.v1`: per-generation leaderboards
  (prompt id + fitness + a prompt excerpt), the champion prompt + lineage, and
  the fitness trajectory.

Fixed opponents (not co-evolving both sides) keeps LLM call volume tractable for
a BYOK run and gives a clean monotone signal; full prompt-vs-prompt co-evolution
can plug into M9's engine via its existing `agent_factory` seam later.

## CLI

`opennego evolve-prompts --role buyer --generations G --population P --model M
[--seed N] [--report PATH]` runs the BYOK loop on the configured LiteLLM
endpoint (key read from env, write-only, never persisted). A `--fake` flag runs
the deterministic no-key path for demos and CI.

## Scope

1. `PromptMutatorPort` + `FakePromptMutator` + `LLMPromptMutator`; the prompt→
   agent factories (LLM BYOK; deterministic fake).
2. `run_prompt_evolution` loop + `opennego.prompt_evolution.v1` (no-key tested
   via fakes; monotone elite fitness asserted).
3. `opennego evolve-prompts` CLI (BYOK + `--fake`) + a generational report +
   README/roadmap.

Out: hosted/multiplayer, protocol v2. The live model quality is the user's to
evaluate with their key.

Design-doc-first, integration-train discipline as M1–M10.
