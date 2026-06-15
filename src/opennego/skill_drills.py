"""Market skill drills (see docs/design/market.md).

Controlled, seed-reproducible, no-key exercises that score one market skill in
isolation before the agent faces the live sandbox. The first drill is listing
selection: pick the listing with the most *attainable* surplus, which is not
always the lowest asking price — a too-cheap listing from a low-reputation
seller carries risk that eats the apparent bargain.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from opennego.artifacts import to_jsonable, write_json

SKILL_DRILL_SCHEMA_VERSION = "opennego.skill_drill.v1"

# Realizable-surplus discount by seller reputation: low reputation means return
# and dispute risk that erodes the apparent bargain.
_RATING_RISK = {"high": 0.0, "medium": 0.06, "low": 0.18, "unknown": 0.10}


class SkillDrillError(ValueError):
    """Raised when a drill cannot be generated or scored."""


@dataclass(frozen=True)
class DrillListing:
    """One candidate listing. ``attainable_surplus`` is ground truth, hidden
    from the selector via :meth:`card`."""

    listing_id: str
    asking_price: float
    condition: str
    listing_age_days: int
    seller_rating_band: str
    market_reference: float
    attainable_surplus: float

    def card(self) -> Mapping[str, object]:
        """The selector-visible fields (no ground-truth surplus)."""

        return {
            "listing_id": self.listing_id,
            "asking_price": self.asking_price,
            "condition": self.condition,
            "listing_age_days": self.listing_age_days,
            "seller_rating_band": self.seller_rating_band,
            "market_reference": self.market_reference,
        }


@dataclass(frozen=True)
class SelectionDrill:
    seed: int
    market_reference: float
    listings: tuple[DrillListing, ...]

    @property
    def optimal_index(self) -> int:
        return max(
            range(len(self.listings)),
            key=lambda i: self.listings[i].attainable_surplus,
        )

    def cards(self) -> tuple[Mapping[str, object], ...]:
        return tuple(listing.card() for listing in self.listings)


@dataclass(frozen=True)
class SkillDrillResult:
    schema_version: str
    drill: str
    seed: int
    score: float
    chosen_index: int
    optimal_index: int
    chosen_attainable_surplus: float
    optimal_attainable_surplus: float
    policy: str


# A selection policy sees only the public cards and returns a chosen index.
SelectionPolicy = Callable[[Sequence[Mapping[str, object]]], int]


def generate_selection_drill(
    *,
    seed: int,
    count: int = 5,
    market_reference: float = 575.0,
) -> SelectionDrill:
    """Build a deterministic listing-selection drill."""

    if count < 2:
        raise SkillDrillError("count: expected at least two listings")
    rng = random.Random(f"selection:{seed}")
    listings = []
    for index in range(count):
        # Asking spans clearly-over-market to suspiciously-cheap.
        asking_fraction = rng.uniform(0.80, 1.15)
        asking = round(market_reference * asking_fraction, 2)
        age = rng.randint(1, 60)
        rating = rng.choice(("high", "high", "medium", "low"))
        # Older listings = more motivated sellers = more room to negotiate.
        age_motivation = market_reference * 0.0015 * age
        risk = market_reference * _RATING_RISK[rating]
        attainable = max(
            0.0,
            (market_reference - asking) + age_motivation - risk,
        )
        listings.append(
            DrillListing(
                listing_id=f"L{index}",
                asking_price=asking,
                condition="used_good",
                listing_age_days=age,
                seller_rating_band=rating,
                market_reference=market_reference,
                attainable_surplus=round(attainable, 2),
            )
        )
    return SelectionDrill(
        seed=seed,
        market_reference=market_reference,
        listings=tuple(listings),
    )


def score_selection(drill: SelectionDrill, chosen_index: int) -> float:
    """Chosen attainable surplus relative to the optimum, in [0, 1]."""

    if not 0 <= chosen_index < len(drill.listings):
        raise SkillDrillError(f"chosen_index out of range: {chosen_index}")
    optimal = drill.listings[drill.optimal_index].attainable_surplus
    chosen = drill.listings[chosen_index].attainable_surplus
    if optimal <= 0:
        # No positive-surplus listing exists: any pick is equally fine.
        return 1.0
    return round(max(0.0, chosen) / optimal, 4)


def lowest_asking_policy(cards: Sequence[Mapping[str, object]]) -> int:
    """Naive baseline: chase the cheapest sticker price (trap-prone)."""

    return min(range(len(cards)), key=lambda i: float(cards[i]["asking_price"]))


def risk_aware_policy(cards: Sequence[Mapping[str, object]]) -> int:
    """Estimate attainable surplus from public signals; the skilled baseline."""

    def estimate(card: Mapping[str, object]) -> float:
        reference = float(card["market_reference"])
        asking = float(card["asking_price"])
        age = float(card["listing_age_days"])
        rating = str(card["seller_rating_band"])
        return (
            (reference - asking)
            + reference * 0.0015 * age
            - reference * _RATING_RISK.get(rating, 0.10)
        )

    return max(range(len(cards)), key=lambda i: estimate(cards[i]))


_POLICIES: Mapping[str, SelectionPolicy] = {
    "risk_aware": risk_aware_policy,
    "lowest_asking": lowest_asking_policy,
}


def run_selection_drill(
    *,
    seed: int,
    count: int = 5,
    market_reference: float = 575.0,
    policy: SelectionPolicy | str = "risk_aware",
    output_path: str | Path | None = None,
) -> SkillDrillResult:
    """Generate a selection drill, run a policy, and score the pick."""

    drill = generate_selection_drill(
        seed=seed, count=count, market_reference=market_reference
    )
    if isinstance(policy, str):
        if policy not in _POLICIES:
            raise SkillDrillError(
                f"unknown policy {policy!r}; available: {sorted(_POLICIES)}"
            )
        policy_name = policy
        policy_fn: SelectionPolicy = _POLICIES[policy]
    else:
        policy_name = getattr(policy, "__name__", "custom")
        policy_fn = policy

    chosen = policy_fn(drill.cards())
    if not isinstance(chosen, int):
        raise SkillDrillError("selection policy must return an integer index")
    result = SkillDrillResult(
        schema_version=SKILL_DRILL_SCHEMA_VERSION,
        drill="listing_selection",
        seed=seed,
        score=score_selection(drill, chosen),
        chosen_index=chosen,
        optimal_index=drill.optimal_index,
        chosen_attainable_surplus=drill.listings[chosen].attainable_surplus,
        optimal_attainable_surplus=(
            drill.listings[drill.optimal_index].attainable_surplus
        ),
        policy=policy_name,
    )
    if output_path is not None:
        write_json(Path(output_path), to_jsonable(result))
    return result
