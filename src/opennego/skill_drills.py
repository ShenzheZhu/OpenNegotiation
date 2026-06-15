"""Market skill drills (see docs/design/market.md).

Controlled, seed-reproducible, no-key exercises that score one market skill in
isolation before the agent faces the live sandbox.

- Listing selection: pick the listing with the most *attainable* surplus,
  which is not always the lowest asking price — a too-cheap listing from a
  low-reputation seller carries risk that eats the apparent bargain.
- Walk-away timing: cut losses fast against an unwinnable seller, but do not
  bail on a seller who is actually conceding. A trigger-happy policy wins the
  unwinnable case and fails the winnable one; a patient policy times out.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from opennego.artifacts import to_jsonable, write_json
from opennego.environment import NegotiationEnvironment
from opennego.schema import (
    ActionType,
    AgentAction,
    AgentContext,
    MarketReference,
    Product,
    Role,
    Scenario,
)

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


# --- Walk-away timing drill -------------------------------------------------


@dataclass
class WalkawayBuyer:
    """A buyer that walks when the seller is stuck, but stays when it concedes.

    ``patience`` is how many consecutive non-conceding seller offers it
    tolerates before walking away (reject). Low patience cuts losses fast but
    risks bailing on a slow-but-real concession; high patience risks timing
    out against a firm seller. The skill is choosing it well.
    """

    patience: int = 2
    name: str = "walkaway_buyer"
    role: Role = Role.BUYER

    def act(self, context: AgentContext) -> AgentAction:
        events = tuple(context.transcript)
        scenario = context.scenario
        reference = scenario.product.market_reference
        anchor = reference.reference_price if reference else scenario.product.list_price
        willingness = min(scenario.buyer_budget, anchor * 0.95)
        seller_offers = [
            event.offer.price
            for event in events
            if event.role == Role.SELLER
            and event.action_type == ActionType.OFFER
            and event.offer is not None
        ]
        latest = seller_offers[-1] if seller_offers else None

        if latest is not None and latest <= willingness:
            return AgentAction.accept(f"Accepted at ${latest:.2f}.")

        if len(seller_offers) > self.patience:
            recent = seller_offers[-(self.patience + 1):]
            # "Stuck" = no meaningful downward movement over the window.
            if recent[0] - recent[-1] < anchor * 0.01:
                return AgentAction.reject(
                    "Seller is not moving; walking away to avoid wasted turns."
                )

        counter = min(willingness, (latest or anchor) * 0.9)
        return AgentAction.offer_price(round(counter, 2), f"My offer is ${counter:.2f}.")


@dataclass
class _FirmSeller:
    """Never concedes: always restates the list price. Unwinnable."""

    name: str = "firm_seller"
    role: Role = Role.SELLER

    def act(self, context: AgentContext) -> AgentAction:
        list_price = context.scenario.product.list_price
        return AgentAction.offer_price(round(list_price, 2), "Price is firm.")


def _drill_scenario(*, market_reference: float, winnable: bool, max_turns: int) -> Scenario:
    list_price = round(market_reference * 1.2, 2)
    reservation = (
        round(market_reference * 0.85, 2)
        if winnable
        else round(market_reference * 1.15, 2)
    )
    product = Product(
        id="walkaway_item",
        name="Walk-away drill item",
        description="Drill fixture.",
        list_price=list_price,
        wholesale_price=round(market_reference * 0.7, 2),
        condition="used_good",
        market_reference=MarketReference(reference_price=market_reference),
    )
    return Scenario(
        product=product,
        buyer_budget=round(market_reference * 0.95, 2),
        seller_reservation_price=reservation,
        max_turns=max_turns,
    )


@dataclass(frozen=True)
class WalkawayDrillResult:
    schema_version: str
    drill: str
    seed: int
    patience: int
    score: float
    unwinnable_outcome: str
    unwinnable_turns: int
    winnable_outcome: str
    walk_score: float
    stay_score: float


def run_walkaway_drill(
    *,
    seed: int = 13,
    patience: int = 2,
    market_reference: float = 575.0,
    max_turns: int = 10,
    output_path: str | Path | None = None,
) -> WalkawayDrillResult:
    """Score a walk-away policy across an unwinnable and a winnable seller."""

    if patience < 0:
        raise SkillDrillError("patience: expected non-negative")

    unwinnable = _drill_scenario(
        market_reference=market_reference, winnable=False, max_turns=max_turns
    )
    unwinnable_env = NegotiationEnvironment(
        scenario=unwinnable,
        buyer=WalkawayBuyer(patience=patience),
        seller=_FirmSeller(),
    )
    unwinnable_result = unwinnable_env.run()

    winnable = _drill_scenario(
        market_reference=market_reference, winnable=True, max_turns=max_turns
    )
    from opennego.agents import ScriptedSeller

    winnable_env = NegotiationEnvironment(
        scenario=winnable,
        buyer=WalkawayBuyer(patience=patience),
        seller=ScriptedSeller(),
    )
    winnable_result = winnable_env.run()

    # Unwinnable: reward a decisive early walk; timeout is the worst.
    if unwinnable_result.outcome in {"rejected", "ghosted"}:
        walk_score = round(
            (max_turns - unwinnable_result.completed_turns) / max_turns, 4
        )
        walk_score = max(0.0, min(1.0, walk_score))
    else:
        walk_score = 0.0
    # Winnable: reward closing; bailing forfeits a real deal.
    if winnable_result.outcome == "deal":
        stay_score = 1.0
    elif winnable_result.outcome == "timeout":
        stay_score = 0.5
    else:
        stay_score = 0.0

    result = WalkawayDrillResult(
        schema_version=SKILL_DRILL_SCHEMA_VERSION,
        drill="walkaway",
        seed=seed,
        patience=patience,
        score=round(0.5 * walk_score + 0.5 * stay_score, 4),
        unwinnable_outcome=unwinnable_result.outcome,
        unwinnable_turns=unwinnable_result.completed_turns,
        winnable_outcome=winnable_result.outcome,
        walk_score=walk_score,
        stay_score=stay_score,
    )
    if output_path is not None:
        write_json(Path(output_path), to_jsonable(result))
    return result


# --- Multi-thread coordination drill ----------------------------------------


@dataclass
class _LowballConvergeBuyer:
    """Opens with a lowball and steps up toward willingness each round.

    Opening low (rather than at willingness) means each seller's distinct
    reservation produces a distinct close, so shopping across threads beats
    committing to one. The behavior is identical in every thread — the skill
    being tested lives in *which* close the agent commits to, not in the
    per-thread tactics.
    """

    name: str = "lowball_buyer"
    role: Role = Role.BUYER

    def act(self, context: AgentContext) -> AgentAction:
        events = tuple(context.transcript)
        scenario = context.scenario
        reference = scenario.product.market_reference
        anchor = reference.reference_price if reference else scenario.product.list_price
        willingness = min(scenario.buyer_budget, anchor * 0.95)
        seller_offer = None
        own_offers = 0
        for event in events:
            if event.role == Role.SELLER and event.action_type == ActionType.OFFER:
                if event.offer is not None:
                    seller_offer = event.offer.price
            elif event.role == Role.BUYER and event.action_type == ActionType.OFFER:
                own_offers += 1
        # Hold out for a disciplined target below willingness: only sellers
        # whose reservation is at or below it will close, so distinct
        # reservations produce distinct outcomes (cheap close vs dead-end).
        target = min(willingness, anchor * 0.82)
        if seller_offer is not None and seller_offer <= target:
            return AgentAction.accept(f"Accepted at ${seller_offer:.2f}.")
        floor = anchor * 0.72
        offer = min(target, floor + (target - floor) * 0.34 * own_offers)
        return AgentAction.offer_price(round(offer, 2), f"My offer is ${offer:.2f}.")


@dataclass(frozen=True)
class MultiThreadDrillResult:
    schema_version: str
    drill: str
    seed: int
    coordinated: bool
    score: float
    closed_price: float | None
    best_attainable_price: float
    thread_count: int
    closed_prices: tuple[float, ...]


def run_multithread_drill(
    *,
    seed: int = 13,
    thread_count: int = 3,
    market_reference: float = 575.0,
    coordinate: bool = True,
    max_turns: int = 12,
    output_path: str | Path | None = None,
) -> MultiThreadDrillResult:
    """Interleave concurrent seller threads via ``step()`` and score the close.

    ``coordinate=True`` shops every thread and commits to the best (lowest)
    deal; ``coordinate=False`` works only the first listing and commits to its
    deal — the no-coordination baseline. Shopping should never close worse.
    """

    from opennego.agents import ScriptedSeller

    if thread_count < 2:
        raise SkillDrillError("thread_count: expected at least two threads")
    rng = random.Random(f"multithread:{seed}")

    threads = []
    reservations = []
    for index in range(thread_count):
        reservation = round(market_reference * rng.uniform(0.75, 0.92), 2)
        reservations.append(reservation)
        base = _drill_scenario(
            market_reference=market_reference, winnable=True, max_turns=max_turns
        )
        scenario = Scenario(
            product=base.product,
            buyer_budget=base.buyer_budget,
            seller_reservation_price=reservation,
            max_turns=max_turns,
        )
        threads.append(
            NegotiationEnvironment(
                scenario=scenario,
                buyer=_LowballConvergeBuyer(),
                seller=ScriptedSeller(),
            )
        )

    # Round-robin interleave: one step per live thread per round. This is the
    # concurrency pattern the M5 scheduler generalizes.
    while any(not env.is_complete for env in threads):
        for env in threads:
            if not env.is_complete:
                env.step()

    deal_prices = [
        env.result.deal_price
        for env in threads
        if env.result is not None
        and env.result.outcome == "deal"
        and env.result.deal_price is not None
    ]
    first_thread = threads[0].result
    first_close = (
        first_thread.deal_price
        if first_thread is not None and first_thread.outcome == "deal"
        else None
    )
    closed_price = (
        (min(deal_prices) if deal_prices else None) if coordinate else first_close
    )
    best_attainable_price = min(reservations)

    if closed_price is None:
        score = 0.0
    else:
        span = max(market_reference - best_attainable_price, 1.0)
        score = round(max(0.0, min(1.0, (market_reference - closed_price) / span)), 4)

    result = MultiThreadDrillResult(
        schema_version=SKILL_DRILL_SCHEMA_VERSION,
        drill="multithread",
        seed=seed,
        coordinated=coordinate,
        score=score,
        closed_price=closed_price,
        best_attainable_price=best_attainable_price,
        thread_count=thread_count,
        closed_prices=tuple(round(p, 2) for p in deal_prices),
    )
    if output_path is not None:
        write_json(Path(output_path), to_jsonable(result))
    return result
