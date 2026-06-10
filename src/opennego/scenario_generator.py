"""Market-grounded scenario generation with BATNA structure.

Private constraints are derived from each side's best alternative to a deal
instead of hand-written constants:

- The buyer's budget comes from the next-best active listing: a price sampled
  from the market reference band plus a switching friction (shipping
  differences, risk, hassle). Paying more than that alternative is irrational.
- The seller's reservation comes from relisting and waiting: an expected
  resale price discounted by patience, minus the cost of relisting, floored
  near the bottom of the observed sold band.

Every derivation is recorded under ``scenario.metadata["batna"]`` so runs are
auditable, and each side's own alternative is surfaced to that agent's
private state by the environment. Sampling is keyed per ``(seed, product,
index)``, so adding or reordering products never changes other scenarios.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from opennego.schema import MarketReference, Product, Scenario

BATNA_SCHEMA_VERSION = "opennego.batna.v1"


class ScenarioGenerationError(ValueError):
    """Raised when scenarios cannot be generated from the given inputs."""


@dataclass(frozen=True)
class GeneratorSettings:
    """Bounds for BATNA derivation. Fraction ranges apply to sampled prices."""

    buyer_friction_range: tuple[float, float] = (0.02, 0.08)
    seller_patience_range: tuple[float, float] = (0.85, 0.97)
    seller_relist_cost_range: tuple[float, float] = (0.03, 0.10)
    seller_floor_fraction: float = 0.85
    max_turns: int = 8

    def __post_init__(self) -> None:
        for name in (
            "buyer_friction_range",
            "seller_patience_range",
            "seller_relist_cost_range",
        ):
            low, high = getattr(self, name)
            if not 0 <= low <= high:
                raise ScenarioGenerationError(f"{name}: expected 0 <= low <= high")
        if not 0 < self.seller_floor_fraction <= 1:
            raise ScenarioGenerationError("seller_floor_fraction: expected in (0, 1]")
        if self.max_turns <= 0:
            raise ScenarioGenerationError("max_turns: expected positive")


def load_products(path: str | Path) -> tuple[Product, ...]:
    records = json.loads(Path(path).read_text())
    if not isinstance(records, list) or not records:
        raise ScenarioGenerationError(f"{path}: expected a non-empty product list")
    return tuple(Product.from_mapping(record) for record in records)


def generate_scenarios(
    products: Sequence[Product],
    *,
    seed: int,
    scenarios_per_product: int = 1,
    settings: GeneratorSettings | None = None,
) -> tuple[Scenario, ...]:
    """Generate seeded scenarios with BATNA-derived private constraints."""

    if not products:
        raise ScenarioGenerationError("expected at least one product")
    if scenarios_per_product <= 0:
        raise ScenarioGenerationError("scenarios_per_product: expected positive")
    settings = settings or GeneratorSettings()

    scenarios = []
    for product in products:
        if product.market_reference is None:
            raise ScenarioGenerationError(
                f"product {product.id!r} has no market_reference; "
                "BATNA derivation requires sold-comps evidence"
            )
        for index in range(scenarios_per_product):
            scenarios.append(
                _generate_one(product, seed=seed, index=index, settings=settings)
            )
    return tuple(scenarios)


def _generate_one(
    product: Product,
    *,
    seed: int,
    index: int,
    settings: GeneratorSettings,
) -> Scenario:
    rng = random.Random(f"{seed}:{product.id}:{index}")
    reference = product.market_reference
    assert reference is not None
    band_low, band_high = _reference_band(reference)

    alternative_price = round(rng.uniform(band_low, band_high), 2)
    friction = round(
        alternative_price * rng.uniform(*settings.buyer_friction_range), 2
    )
    buyer_budget = round(alternative_price + friction, 2)

    expected_resale = round(
        reference.reference_price * rng.uniform(*settings.seller_patience_range), 2
    )
    relist_cost = round(
        expected_resale * rng.uniform(*settings.seller_relist_cost_range), 2
    )
    reservation_floor = round(band_low * settings.seller_floor_fraction, 2)
    seller_reservation = max(round(expected_resale - relist_cost, 2), reservation_floor)

    batna = {
        "schema_version": BATNA_SCHEMA_VERSION,
        "seed": seed,
        "index": index,
        "buyer": {
            "basis": "next_best_active_listing",
            "alternative_price": alternative_price,
            "switching_friction": friction,
            "derived_budget": buyer_budget,
        },
        "seller": {
            "basis": "relist_and_wait",
            "expected_resale_price": expected_resale,
            "relist_cost": relist_cost,
            "reservation_floor": reservation_floor,
            "derived_reservation": seller_reservation,
        },
        "source": {
            "reference_price": reference.reference_price,
            "p25_price": reference.p25_price,
            "p75_price": reference.p75_price,
            "sample_size": reference.sample_size,
            "window_days": reference.window_days,
            "source": reference.source,
        },
    }
    return Scenario(
        product=product,
        buyer_budget=buyer_budget,
        seller_reservation_price=seller_reservation,
        max_turns=settings.max_turns,
        metadata={
            "scenario_id": f"{product.id}-batna-s{seed}-{index}",
            "generator": "opennego.scenario_generator",
            "batna": batna,
        },
    )


def _reference_band(reference: MarketReference) -> tuple[float, float]:
    low = reference.p25_price
    high = reference.p75_price
    if low is None or high is None or high <= low:
        low = reference.reference_price * 0.9
        high = reference.reference_price * 1.1
    return low, high
