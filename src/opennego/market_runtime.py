"""Market concurrency scheduler and clearing (see docs/design/market.md).

Runs many buyer-seller threads over a ``MarketState`` at once by interleaving
each thread's ``NegotiationEnvironment.step()`` round-robin — the payoff of the
steppable environment from M1. When a thread closes a deal the market clears:
the listing is marked sold, every other buyer's thread on that listing ends
(``listing_taken``), and the winning buyer's other threads end
(``bought_elsewhere``). Per-side scores ingest into the rating store.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import to_jsonable, write_json
from opennego.environment import NegotiationEnvironment
from opennego.market import Listing, MarketState, mark_sold
from opennego.quality import condition_to_quality
from opennego.rating import RatingStore, compute_match_score
from opennego.schema import (
    ActionType,
    MarketReference,
    Product,
    Role,
    Scenario,
)

MARKET_EPISODE_SCHEMA_VERSION = "opennego.market_episode.v1"


class MarketRuntimeError(ValueError):
    """Raised when a market episode cannot be run."""


@dataclass
class _Thread:
    thread_id: str
    buyer_id: str
    listing_id: str
    seller_id: str
    env: NegotiationEnvironment
    scenario: Scenario
    status: str = "open"  # open | deal | rejected | timeout | ghosted | cancelled
    deal_price: float | None = None
    cancel_reason: str | None = None


@dataclass(frozen=True)
class MarketEpisodeResult:
    schema_version: str
    seed: int
    buyer_count: int
    listing_count: int
    thread_count: int
    deals: int
    cancellations: int
    clearings: tuple[Mapping[str, Any], ...]
    threads: tuple[Mapping[str, Any], ...]
    participant_outcomes: Mapping[str, Any] = field(default_factory=dict)


def run_market_episode(
    state: MarketState,
    *,
    buyer_ids: Sequence[str],
    shortlist_size: int = 3,
    max_turns: int = 8,
    seed: int = 13,
    store: RatingStore | None = None,
    episode_id: str = "episode",
    output_path: str | Path | None = None,
) -> MarketEpisodeResult:
    """Run concurrent buyer-seller threads over the market and clear deals."""

    if not buyer_ids:
        raise MarketRuntimeError("buyer_ids: expected at least one buyer")
    active_listings = state.active()
    if not active_listings:
        raise MarketRuntimeError("market has no active listings")

    rng = random.Random(f"market_episode:{seed}")
    threads = _open_threads(
        buyer_ids=buyer_ids,
        listings=active_listings,
        shortlist_size=shortlist_size,
        max_turns=max_turns,
        rng=rng,
    )

    clearings: list[Mapping[str, Any]] = []
    market = state
    # Round-robin interleave until every thread is resolved.
    while any(thread.status == "open" for thread in threads):
        for thread in threads:
            if thread.status != "open":
                continue
            thread.env.step()
            if thread.env.is_complete:
                _resolve_completed(thread)
                if thread.status == "deal":
                    market = _clear(market, thread, threads, clearings)

    if store is not None:
        _ingest(threads, store=store, episode_id=episode_id)

    result = MarketEpisodeResult(
        schema_version=MARKET_EPISODE_SCHEMA_VERSION,
        seed=seed,
        buyer_count=len(set(buyer_ids)),
        listing_count=len(active_listings),
        thread_count=len(threads),
        deals=sum(1 for t in threads if t.status == "deal"),
        cancellations=sum(1 for t in threads if t.status == "cancelled"),
        clearings=tuple(clearings),
        threads=tuple(_thread_summary(t) for t in threads),
        participant_outcomes=_participant_outcomes(threads),
    )
    if output_path is not None:
        write_json(Path(output_path), to_jsonable(result))
    return result


def _open_threads(
    *,
    buyer_ids: Sequence[str],
    listings: Sequence[Listing],
    shortlist_size: int,
    max_turns: int,
    rng: random.Random,
) -> list[_Thread]:
    threads: list[_Thread] = []
    # Best apparent deals first, so buyers contend over the same good listings.
    ranked = sorted(listings, key=lambda l: l.asking_price - l.reference_price)
    for buyer_id in dict.fromkeys(buyer_ids):
        for listing in ranked[:shortlist_size]:
            scenario = _thread_scenario(listing, max_turns=max_turns, rng=rng)
            env = NegotiationEnvironment(
                scenario=scenario,
                buyer=ToolAwareBuyer(name=buyer_id),
                seller=ScriptedSeller(name=listing.seller_participant_id),
            )
            threads.append(
                _Thread(
                    thread_id=f"{buyer_id}__{listing.listing_id}",
                    buyer_id=buyer_id,
                    listing_id=listing.listing_id,
                    seller_id=listing.seller_participant_id,
                    env=env,
                    scenario=scenario,
                )
            )
    return threads


def _thread_scenario(
    listing: Listing,
    *,
    max_turns: int,
    rng: random.Random,
) -> Scenario:
    reference = listing.reference_price
    reservation = round(reference * rng.uniform(0.80, 0.90), 2)
    product = Product(
        id=listing.product_id,
        name=listing.title,
        description="Market listing.",
        list_price=listing.asking_price,
        wholesale_price=round(reference * 0.7, 2),
        condition=listing.condition,
        market_reference=MarketReference(reference_price=reference),
    )
    return Scenario(
        product=product,
        buyer_budget=round(reference * 0.95, 2),
        seller_reservation_price=reservation,
        max_turns=max_turns,
    )


def _resolve_completed(thread: _Thread) -> None:
    result = thread.env.result
    assert result is not None
    thread.status = result.outcome if result.outcome in {
        "deal",
        "rejected",
        "timeout",
        "ghosted",
    } else "rejected"
    thread.deal_price = result.deal_price


def _clear(
    market: MarketState,
    winning: _Thread,
    threads: list[_Thread],
    clearings: list[Mapping[str, Any]],
) -> MarketState:
    """Settle a deal and cancel conflicting open threads."""

    updated = mark_sold(market, winning.listing_id)
    cancelled_buyer = []
    cancelled_listing = []
    for thread in threads:
        if thread is winning or thread.status != "open":
            continue
        if thread.listing_id == winning.listing_id:
            thread.status = "cancelled"
            thread.cancel_reason = "listing_taken"
            cancelled_listing.append(thread.thread_id)
        elif thread.buyer_id == winning.buyer_id:
            thread.status = "cancelled"
            thread.cancel_reason = "bought_elsewhere"
            cancelled_buyer.append(thread.thread_id)
    clearings.append(
        {
            "thread_id": winning.thread_id,
            "buyer_id": winning.buyer_id,
            "listing_id": winning.listing_id,
            "deal_price": winning.deal_price,
            "cancelled_listing_threads": cancelled_listing,
            "cancelled_buyer_threads": cancelled_buyer,
        }
    )
    return updated


def _ingest(
    threads: Sequence[_Thread],
    *,
    store: RatingStore,
    episode_id: str,
) -> None:
    for thread in threads:
        if thread.status not in {"deal", "rejected", "timeout", "ghosted"}:
            continue
        scenario = thread.scenario
        reference = scenario.product.market_reference
        ghost_walker = _ghost_walker(thread)
        score = compute_match_score(
            outcome=thread.status,
            deal_price=thread.deal_price,
            buyer_budget=scenario.buyer_budget,
            seller_reservation=scenario.seller_reservation_price,
            market_reference=reference.reference_price if reference else None,
            ghost_walker=ghost_walker,
            true_quality=scenario.seller_true_quality,
            claimed_quality=condition_to_quality(scenario.product.condition),
        )
        store.ingest_match(
            run_id=f"{episode_id}::{thread.thread_id}",
            scenario_id=thread.listing_id,
            buyer_participant_id=thread.buyer_id,
            seller_participant_id=thread.seller_id,
            outcome=thread.status,
            deal_price=thread.deal_price,
            score=score,
        )


def _ghost_walker(thread: _Thread) -> Role | None:
    result = thread.env.result
    if result is None:
        return None
    for event in reversed(result.events):
        if event.action_type == ActionType.GHOST:
            return event.role
    return None


def _thread_summary(thread: _Thread) -> Mapping[str, Any]:
    result = thread.env.result
    return {
        "thread_id": thread.thread_id,
        "buyer_id": thread.buyer_id,
        "listing_id": thread.listing_id,
        "seller_id": thread.seller_id,
        "status": thread.status,
        "deal_price": thread.deal_price,
        "completed_turns": result.completed_turns if result is not None else None,
        "cancel_reason": thread.cancel_reason,
    }


def _participant_outcomes(threads: Sequence[_Thread]) -> Mapping[str, Any]:
    buyers: dict[str, dict[str, Any]] = {}
    for thread in threads:
        record = buyers.setdefault(
            thread.buyer_id, {"deals": 0, "spend": 0.0, "threads": 0}
        )
        record["threads"] += 1
        if thread.status == "deal" and thread.deal_price is not None:
            record["deals"] += 1
            record["spend"] = round(record["spend"] + thread.deal_price, 2)
    return buyers
