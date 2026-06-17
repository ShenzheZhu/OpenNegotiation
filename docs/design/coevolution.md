# Co-evolution: Competing Populations and an Evolving Meta

Status: **accepted — milestone M9, in progress.** The "a2a adversarial play +
prompt evolution" headline: instead of training against a fixed NPC roster,
populations of buyer and seller strategies play each other and evolve in
response, so strategies are validated against a *moving* adversary rather than a
static one.

## Why

Every milestone so far trains against the **fixed** curated roster. A strategy
that tops that roster may simply have over-fit it (the failure M2's held-out
validation guards against, and M8 ranks candidates by). Co-evolution removes the
fixed opponent: buyer strategies evolve to beat the current seller strategies,
which evolve to beat the buyers — an arms race whose champions are robust
*because* their opponents kept adapting. It also surfaces the **meta**: a
dominant style emerges, gets countered, and the cycle repeats.

## The fitness fork (resolved)

Evolution needs a fitness signal that moves when a strategy mutates.

- **Deterministic parameter genome (core, no-key).** Evolve a bounded numeric
  genome the existing deterministic agents already consume — buyer
  `opening_discount` / `counter_fraction` / `willingness_multiplier` /
  `quality_skepticism`; seller `opening_markup` / `concession_fraction` /
  `floor_reference_multiplier`. Mutating these genuinely changes outcomes, so
  the arms race is real and **fully reproducible in CI without any API key**.
- **Prompt genome (optional, BYOK).** Evolve strategy *prompts* on the same
  loop. Deterministic agents ignore prompts, so fitness only moves when matches
  run through an LLM agent — this layer needs the user's key and is **not** part
  of the no-key CI proof. It plugs into the identical generational engine via an
  agent-factory seam; only the genome representation and the agent differ.

The core ships deterministic; the prompt layer is a gated extension.

## Model

- **Two populations** keyed by role: buyers and sellers (the rating store
  already keeps separate buyer/seller tracks). Each is a list of genomes.
- **Tournament (one generation).** Every buyer genome plays every seller genome
  on a fixed seeded scenario set; each match is scored with the existing
  quality/reputation-aware `compute_match_score`. A genome's fitness is its mean
  role-score across its matches. Optionally the matches are ingested into a
  `RatingStore` for an Elo view.
- **Select / vary / cull.** Within each population keep the top fraction
  (elites), fill the rest by mutating elites (seeded Gaussian perturbation
  clamped to gene bounds) and crossover (per-gene parent choice). Deterministic
  in the generation seed.
- **Generations.** Repeat for `G` generations, recording per-generation
  leaderboards, the champion genome per role, and the mean/best fitness
  trajectory (does the population improve? does the meta swing?).
- **Lineage.** Each champion records its parent genome ids, so the winning
  line is auditable end to end.

## Artifacts

- `opennego.coevolution.v1` — the full run: config, per-generation buyer/seller
  leaderboards, champion genomes + lineage, and the fitness trajectory.

## CLI

`opennego coevolve --generations G --population P [--seed N] [--report PATH]`
emits the artifact as JSON and an optional static HTML report (per-generation
leaderboards + champion lineage + trajectory). Deterministic and no-key.

## Scope

In: the deterministic genome + evolved agents, the tournament, the generational
engine, the artifact, the CLI, and a report. A BYOK prompt-genome **seam** (an
agent factory the engine calls) so the LLM layer can be added without touching
the core.

Out: the live LLM prompt-evolution implementation itself (BYOK, separate,
key-gated), protocol v2, hosted/multiplayer.

## Issues

1. Genome + evolved deterministic agents + seeded variation operators.
2. Tournament + generational engine (`run_coevolution`) + `coevolution.v1`.
3. `opennego coevolve` CLI, the generational report, and the BYOK agent-factory
   seam.

Design-doc-first, integration-train discipline as M1–M8.
