"""Co-evolution substrate: evolvable strategy genomes and variation.

A genome is a bounded numeric point in the policy space the deterministic
profile agents already consume (see ``opennego.agents.profiles``). It maps to a
``BuyerPolicy`` / ``SellerPolicy`` and drives a real agent, so mutating it
genuinely changes match outcomes — the property the co-evolution engine needs
to run a reproducible, no-key arms race (see ``docs/design/coevolution.md``).

Variation (``mutate`` / ``crossover``) is deterministic in a supplied
``random.Random``, so an entire run replays identically from its seed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from opennego.agents.profiles import (
    BuyerPolicy,
    ProfileBackedBuyer,
    ProfileBackedSeller,
    SellerPolicy,
)
from opennego.artifacts import to_jsonable, write_json
from opennego.environment import NegotiationEnvironment
from opennego.learning import StrategyProfile
from opennego.rating import compute_match_score
from opennego.scenario_generator import generate_scenarios, load_products
from opennego.schema import Role, Scenario

COEVOLUTION_SCHEMA_VERSION = "opennego.coevolution.v1"
COEVOLUTION_EXECUTION_MODE = "competitive_population_tournament_v1"
DEFAULT_PRODUCTS_PATH = "examples/data/real_market_products.json"

# Maps a genome to the agent that plays it. The default deterministic factory is
# build_agent; the BYOK prompt layer supplies its own factory (e.g. one that
# builds an LLM agent from a prompt genome) to run on the same engine.
AgentFactory = Callable[["Genome"], Any]

# Gene bounds per role: (low, high), inclusive. The genome carries exactly these
# keys; anything else is rejected so a genome can never smuggle in a non-evolved
# policy field.
GENE_BOUNDS: Mapping[Role, Mapping[str, tuple[float, float]]] = {
    Role.BUYER: {
        "opening_discount": (0.50, 0.95),
        "counter_fraction": (0.60, 0.95),
        "willingness_multiplier": (0.80, 1.00),
        "quality_skepticism": (0.00, 0.30),
    },
    Role.SELLER: {
        "opening_markup": (0.85, 1.00),
        "concession_fraction": (0.20, 0.70),
        "floor_reference_multiplier": (0.90, 1.10),
    },
}


class CoevolutionError(ValueError):
    """Raised when a genome or variation request is invalid."""


@dataclass(frozen=True)
class Genome:
    genome_id: str
    role: Role
    genes: Mapping[str, float]
    parent_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        role = Role(self.role)
        object.__setattr__(self, "role", role)
        expected = set(GENE_BOUNDS[role])
        got = set(self.genes)
        if got != expected:
            raise CoevolutionError(
                f"{role.value} genome genes {sorted(got)} != {sorted(expected)}"
            )
        # Store clamped, rounded genes so equality and artifacts are stable.
        object.__setattr__(
            self,
            "genes",
            {
                name: round(_clamp(float(self.genes[name]), *GENE_BOUNDS[role][name]), 6)
                for name in GENE_BOUNDS[role]
            },
        )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def to_policy(genome: Genome) -> BuyerPolicy | SellerPolicy:
    """Build the deterministic policy a genome encodes."""

    if genome.role == Role.BUYER:
        return BuyerPolicy(**genome.genes)
    return SellerPolicy(**genome.genes)


def _synthetic_profile(role: Role, genome_id: str) -> StrategyProfile:
    return StrategyProfile(
        id=genome_id,
        name=f"evolved_{role.value}_{genome_id}",
        role=role,
        archetype="evolved",
        difficulty="evolved",
        summary="Co-evolved strategy genome.",
        base_prompt="Follow OpenNegotiation protocol exactly.",
        strategy_prompt="Evolved deterministic policy.",
    )


def build_agent(genome: Genome):
    """Construct a deterministic agent driven by the genome's policy."""

    profile = _synthetic_profile(genome.role, genome.genome_id)
    policy = to_policy(genome)
    if genome.role == Role.BUYER:
        return ProfileBackedBuyer(profile=profile, policy_override=policy)
    return ProfileBackedSeller(profile=profile, policy_override=policy)


def random_genome(role: Role, rng: random.Random, *, genome_id: str) -> Genome:
    """Sample a uniform genome within the role's gene bounds."""

    role = Role(role)
    genes = {
        name: rng.uniform(low, high) for name, (low, high) in GENE_BOUNDS[role].items()
    }
    return Genome(genome_id=genome_id, role=role, genes=genes)


def mutate(
    genome: Genome,
    rng: random.Random,
    *,
    genome_id: str,
    rate: float = 0.5,
    scale: float = 0.15,
) -> Genome:
    """Perturb each gene with probability ``rate`` by a clamped Gaussian step.

    ``scale`` is a fraction of each gene's range, so the step size is
    comparable across genes. Deterministic in ``rng``.
    """

    bounds = GENE_BOUNDS[genome.role]
    genes = dict(genome.genes)
    for name, (low, high) in bounds.items():
        if rng.random() <= rate:
            step = rng.gauss(0.0, scale * (high - low))
            genes[name] = _clamp(genes[name] + step, low, high)
    return Genome(
        genome_id=genome_id,
        role=genome.role,
        genes=genes,
        parent_ids=(genome.genome_id,),
    )


def crossover(
    parent_a: Genome,
    parent_b: Genome,
    rng: random.Random,
    *,
    genome_id: str,
) -> Genome:
    """Per-gene uniform crossover of two same-role parents."""

    if parent_a.role != parent_b.role:
        raise CoevolutionError("crossover requires genomes of the same role")
    genes = {
        name: (parent_a.genes[name] if rng.random() < 0.5 else parent_b.genes[name])
        for name in GENE_BOUNDS[parent_a.role]
    }
    return Genome(
        genome_id=genome_id,
        role=parent_a.role,
        genes=genes,
        parent_ids=(parent_a.genome_id, parent_b.genome_id),
    )


# --- tournament + generational engine ---------------------------------------


@dataclass(frozen=True)
class GenomeScore:
    genome_id: str
    fitness: float
    genes: Mapping[str, float]
    parent_ids: tuple[str, ...]


@dataclass(frozen=True)
class GenerationRecord:
    generation: int
    buyer_leaderboard: tuple[GenomeScore, ...]
    seller_leaderboard: tuple[GenomeScore, ...]
    buyer_best_fitness: float
    seller_best_fitness: float
    buyer_mean_fitness: float
    seller_mean_fitness: float


@dataclass(frozen=True)
class Coevolution:
    schema_version: str
    execution_mode: str
    seed: int
    generations: int
    population_size: int
    scenario_count: int
    evolve_roles: tuple[str, ...]
    generation_records: tuple[GenerationRecord, ...]
    buyer_champion: GenomeScore
    seller_champion: GenomeScore
    buyer_champion_lineage: tuple[Mapping[str, Any], ...]
    seller_champion_lineage: tuple[Mapping[str, Any], ...]
    trajectory: Mapping[str, Any]
    artifact_path: str


def run_coevolution(
    *,
    output_dir: str | Path = "runs/coevolution",
    products_path: str | Path = DEFAULT_PRODUCTS_PATH,
    generations: int = 5,
    population: int = 6,
    scenario_count: int = 2,
    seed: int = 13,
    evolve: Sequence[str] = ("buyer", "seller"),
    elite_fraction: float = 0.34,
    scenarios: Sequence[Scenario] | None = None,
    agent_factory: AgentFactory | None = None,
) -> Coevolution:
    """Run a competitive co-evolution: two populations, G generations.

    Each generation every buyer genome plays every seller genome on the
    scenario set; fitness is the mean role-score. Within each evolving role the
    elites survive and the rest are refilled by mutation/crossover (deterministic
    in ``seed``). A role omitted from ``evolve`` is held fixed across
    generations — fixing one side makes the other side's improvement monotone,
    which is how the engine is regression-tested.
    """

    if population < 2:
        raise CoevolutionError("population: expected at least two genomes per role")
    if generations < 1:
        raise CoevolutionError("generations: expected at least one generation")
    evolve_set = {str(role) for role in evolve}
    if not evolve_set <= {"buyer", "seller"}:
        raise CoevolutionError("evolve: expected a subset of {'buyer', 'seller'}")

    if scenarios is None:
        products = load_products(products_path)
        scenarios = generate_scenarios(
            products[:1] or products, seed=seed, scenarios_per_product=scenario_count
        )
    scenarios = tuple(scenarios)
    if not scenarios:
        raise CoevolutionError("no scenarios available for the tournament")

    factory = agent_factory or build_agent
    rng = random.Random(f"coevolution:{seed}")
    registry: dict[str, Genome] = {}

    def _seed_population(role: Role) -> list[Genome]:
        pop = []
        for index in range(population):
            genome = random_genome(role, rng, genome_id=f"g0-{role.value}-{index}")
            registry[genome.genome_id] = genome
            pop.append(genome)
        return pop

    buyers = _seed_population(Role.BUYER)
    sellers = _seed_population(Role.SELLER)

    generation_records: list[GenerationRecord] = []
    for generation in range(generations):
        buyer_fit, seller_fit = _tournament(buyers, sellers, scenarios, factory)
        buyer_board = _leaderboard(buyers, buyer_fit)
        seller_board = _leaderboard(sellers, seller_fit)
        generation_records.append(
            GenerationRecord(
                generation=generation,
                buyer_leaderboard=buyer_board,
                seller_leaderboard=seller_board,
                buyer_best_fitness=buyer_board[0].fitness,
                seller_best_fitness=seller_board[0].fitness,
                buyer_mean_fitness=round(
                    sum(s.fitness for s in buyer_board) / len(buyer_board), 6
                ),
                seller_mean_fitness=round(
                    sum(s.fitness for s in seller_board) / len(seller_board), 6
                ),
            )
        )
        if generation < generations - 1:
            if "buyer" in evolve_set:
                buyers = _next_generation(
                    buyer_board, registry, rng, generation + 1, Role.BUYER, elite_fraction
                )
            if "seller" in evolve_set:
                sellers = _next_generation(
                    seller_board, registry, rng, generation + 1, Role.SELLER, elite_fraction
                )

    final = generation_records[-1]
    buyer_champion = final.buyer_leaderboard[0]
    seller_champion = final.seller_leaderboard[0]

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifact_path = output / "coevolution.json"
    result = Coevolution(
        schema_version=COEVOLUTION_SCHEMA_VERSION,
        execution_mode=COEVOLUTION_EXECUTION_MODE,
        seed=seed,
        generations=generations,
        population_size=population,
        scenario_count=len(scenarios),
        evolve_roles=tuple(sorted(evolve_set)),
        generation_records=tuple(generation_records),
        buyer_champion=buyer_champion,
        seller_champion=seller_champion,
        buyer_champion_lineage=_lineage(buyer_champion.genome_id, registry),
        seller_champion_lineage=_lineage(seller_champion.genome_id, registry),
        trajectory={
            "buyer_best_by_generation": [r.buyer_best_fitness for r in generation_records],
            "seller_best_by_generation": [
                r.seller_best_fitness for r in generation_records
            ],
        },
        artifact_path=str(artifact_path),
    )
    write_json(artifact_path, to_jsonable(result))
    return result


def render_coevolution_report(result: Coevolution) -> str:
    """Render a self-contained static HTML report for a co-evolution run."""

    import html

    def esc(value: Any) -> str:
        return html.escape(str(value))

    def genes_str(genes: Mapping[str, float]) -> str:
        return ", ".join(f"{k}={v:.3f}" for k, v in genes.items())

    gen_rows = "".join(
        "<tr>"
        f"<td>{r.generation}</td>"
        f"<td>{r.buyer_best_fitness:.4f}</td><td>{r.buyer_mean_fitness:.4f}</td>"
        f"<td>{r.seller_best_fitness:.4f}</td><td>{r.seller_mean_fitness:.4f}</td>"
        f"<td>{esc(r.buyer_leaderboard[0].genome_id)}</td>"
        f"<td>{esc(r.seller_leaderboard[0].genome_id)}</td>"
        "</tr>"
        for r in result.generation_records
    )

    def lineage_list(lineage: Sequence[Mapping[str, Any]]) -> str:
        return "".join(
            f"<li>{esc(item['genome_id'])} "
            f"(parents: {esc(', '.join(item['parent_ids']) or 'seed')})</li>"
            for item in lineage
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Co-evolution run (seed {esc(result.seed)})</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 14px; }}
th {{ background: #f3f4f6; }}
.summary {{ background: #f9fafb; border: 1px solid #e5e7eb; padding: 1rem; border-radius: 6px; }}
code {{ font-size: 13px; }}
</style></head><body>
<h1>Co-evolution run</h1>
<div class="summary">
<p>Seed <strong>{esc(result.seed)}</strong> &middot;
{result.generations} generations &middot; population {result.population_size}/role &middot;
{result.scenario_count} scenarios &middot; evolving: {esc(', '.join(result.evolve_roles))}</p>
<p>Buyer champion <code>{esc(result.buyer_champion.genome_id)}</code>
(fitness {result.buyer_champion.fitness:.4f}): {esc(genes_str(result.buyer_champion.genes))}</p>
<p>Seller champion <code>{esc(result.seller_champion.genome_id)}</code>
(fitness {result.seller_champion.fitness:.4f}): {esc(genes_str(result.seller_champion.genes))}</p>
</div>
<h2>Per-generation fitness</h2>
<table><thead><tr>
<th>Gen</th><th>Buyer best</th><th>Buyer mean</th>
<th>Seller best</th><th>Seller mean</th><th>Buyer leader</th><th>Seller leader</th>
</tr></thead><tbody>{gen_rows}</tbody></table>
<h2>Champion lineage</h2>
<h3>Buyer</h3><ul>{lineage_list(result.buyer_champion_lineage)}</ul>
<h3>Seller</h3><ul>{lineage_list(result.seller_champion_lineage)}</ul>
</body></html>
"""


def _tournament(
    buyers: Sequence[Genome],
    sellers: Sequence[Genome],
    scenarios: Sequence[Scenario],
    factory: AgentFactory,
) -> tuple[dict[str, float], dict[str, float]]:
    buyer_scores: dict[str, list[float]] = {b.genome_id: [] for b in buyers}
    seller_scores: dict[str, list[float]] = {s.genome_id: [] for s in sellers}
    buyer_agents = {b.genome_id: factory(b) for b in buyers}
    seller_agents = {s.genome_id: factory(s) for s in sellers}
    for buyer in buyers:
        for seller in sellers:
            for scenario in scenarios:
                result = NegotiationEnvironment(
                    scenario=scenario,
                    buyer=buyer_agents[buyer.genome_id],
                    seller=seller_agents[seller.genome_id],
                ).run()
                reference = scenario.product.market_reference
                score = compute_match_score(
                    outcome=result.outcome,
                    deal_price=result.deal_price,
                    buyer_budget=scenario.buyer_budget,
                    seller_reservation=scenario.seller_reservation_price,
                    market_reference=reference.reference_price if reference else None,
                    true_quality=scenario.seller_true_quality,
                    claimed_quality=None,
                    reputation_band=(
                        scenario.seller_reputation.band
                        if scenario.seller_reputation is not None
                        else None
                    ),
                )
                buyer_scores[buyer.genome_id].append(score.buyer)
                seller_scores[seller.genome_id].append(score.seller)
    buyer_fit = {gid: _mean(values) for gid, values in buyer_scores.items()}
    seller_fit = {gid: _mean(values) for gid, values in seller_scores.items()}
    return buyer_fit, seller_fit


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _leaderboard(
    population: Sequence[Genome], fitness: Mapping[str, float]
) -> tuple[GenomeScore, ...]:
    scored = [
        GenomeScore(
            genome_id=genome.genome_id,
            fitness=round(fitness[genome.genome_id], 6),
            genes=genome.genes,
            parent_ids=genome.parent_ids,
        )
        for genome in population
    ]
    scored.sort(key=lambda s: (-s.fitness, s.genome_id))
    return tuple(scored)


def _next_generation(
    leaderboard: Sequence[GenomeScore],
    registry: dict[str, Genome],
    rng: random.Random,
    generation: int,
    role: Role,
    elite_fraction: float,
) -> list[Genome]:
    size = len(leaderboard)
    elite_count = max(1, int(round(size * elite_fraction)))
    elites = [registry[s.genome_id] for s in leaderboard[:elite_count]]
    next_pop = list(elites)
    child_index = 0
    while len(next_pop) < size:
        new_id = f"g{generation}-{role.value}-{child_index}"
        if len(elites) >= 2 and rng.random() < 0.5:
            parent_a, parent_b = rng.sample(elites, 2)
            child = crossover(parent_a, parent_b, rng, genome_id=new_id)
        else:
            parent = rng.choice(elites)
            child = mutate(parent, rng, genome_id=new_id)
        registry[child.genome_id] = child
        next_pop.append(child)
        child_index += 1
    return next_pop


def _lineage(
    genome_id: str, registry: Mapping[str, Genome]
) -> tuple[Mapping[str, Any], ...]:
    """Walk parent_ids from a genome back to its seed ancestors."""

    chain: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    frontier = [genome_id]
    while frontier:
        current = frontier.pop(0)
        if current in seen or current not in registry:
            continue
        seen.add(current)
        genome = registry[current]
        chain.append(
            {
                "genome_id": genome.genome_id,
                "parent_ids": list(genome.parent_ids),
                "genes": dict(genome.genes),
            }
        )
        frontier.extend(genome.parent_ids)
    return tuple(chain)
