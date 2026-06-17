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
from typing import Mapping

from opennego.agents.profiles import (
    BuyerPolicy,
    ProfileBackedBuyer,
    ProfileBackedSeller,
    SellerPolicy,
)
from opennego.learning import StrategyProfile
from opennego.schema import Role

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
