"""Staged market autonomy L1-L3 (see docs/design/market.md).

Autonomy is added under control so an agent never faces the full market before
it is ready:

- L1: the runtime assigns one listing; the agent negotiates a single thread.
- L2: the runtime offers a shortlist; the agent selects one and negotiates it.
- L3: the agent free-selects from discovery and negotiates concurrent threads.

Each level runs deterministically and reports a saving-vs-reference metric, so
a user can see which level their agent is reliable at.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from opennego.artifacts import to_jsonable, write_json
from opennego.market import MarketState
from opennego.market_runtime import MarketRuntimeError, run_market_episode
from opennego.rating import RatingStore

MARKET_AUTONOMY_SCHEMA_VERSION = "opennego.market_autonomy.v1"
LEVELS = ("L1", "L2", "L3")

# Saving this fraction off the sold-comps reference on the best deal scores 1.0.
_SAVING_FULL_CREDIT = 0.25


@dataclass(frozen=True)
class AutonomyResult:
    schema_version: str
    level: str
    buyer_id: str
    seed: int
    score: float
    engaged_listings: tuple[str, ...]
    shortlist: tuple[str, ...]
    deals: int
    best_deal_price: float | None
    best_deal_reference: float | None


def run_autonomy_episode(
    state: MarketState,
    *,
    buyer_id: str,
    level: str,
    shortlist_size: int = 3,
    max_turns: int = 8,
    seed: int = 13,
    store: RatingStore | None = None,
    episode_id: str | None = None,
    output_path: str | Path | None = None,
) -> AutonomyResult:
    """Run one autonomy-level episode for a single buyer."""

    if level not in LEVELS:
        raise MarketRuntimeError(f"level: expected one of {LEVELS}, got {level!r}")
    active = state.active()
    if not active:
        raise MarketRuntimeError("market has no active listings")

    reference_by_id = {l.listing_id: l.reference_price for l in active}
    # Discovery ranks best apparent spread first.
    cards = state.discover(limit=max(shortlist_size, 1))
    shortlist: tuple[str, ...] = tuple(c["listing_id"] for c in cards)

    if level == "L1":
        # Runtime assigns the single best-spread listing; no agent choice.
        chosen = shortlist[:1]
        episode_state = _restrict(state, chosen)
        episode_shortlist: tuple[str, ...] = ()
        episode_size = 1
    elif level == "L2":
        # Runtime offers a shortlist; the agent selects one from it.
        selected = _select_from_shortlist(cards)
        chosen = (selected,)
        episode_state = _restrict(state, chosen)
        episode_shortlist = shortlist
        episode_size = 1
    else:  # L3
        chosen = shortlist
        episode_state = state
        episode_shortlist = shortlist
        episode_size = shortlist_size

    episode = run_market_episode(
        episode_state,
        buyer_ids=[buyer_id],
        shortlist_size=episode_size,
        max_turns=max_turns,
        seed=seed,
        store=store,
        episode_id=episode_id or f"autonomy-{level}-{buyer_id}",
    )

    deal_threads = [
        t for t in episode.threads if t["status"] == "deal" and t["deal_price"] is not None
    ]
    best_price = min((t["deal_price"] for t in deal_threads), default=None)
    best_reference = None
    if best_price is not None:
        best_thread = min(deal_threads, key=lambda t: t["deal_price"])
        best_reference = reference_by_id.get(best_thread["listing_id"])

    score = _saving_score(best_price, best_reference)
    result = AutonomyResult(
        schema_version=MARKET_AUTONOMY_SCHEMA_VERSION,
        level=level,
        buyer_id=buyer_id,
        seed=seed,
        score=score,
        engaged_listings=tuple(
            t["listing_id"] for t in episode.threads
        ),
        shortlist=episode_shortlist,
        deals=len(deal_threads),
        best_deal_price=best_price,
        best_deal_reference=best_reference,
    )
    if output_path is not None:
        write_json(Path(output_path), to_jsonable(result))
    return result


def _restrict(state: MarketState, listing_ids: tuple[str, ...]) -> MarketState:
    keep = set(listing_ids)
    listings = tuple(l for l in state.listings if l.listing_id in keep)
    if not listings:
        raise MarketRuntimeError("no listings to engage after restriction")
    return replace(state, listings=listings)


def _select_from_shortlist(cards: tuple[Mapping[str, Any], ...]) -> str:
    """Pick the listing with the best spread vs reference from the shortlist."""

    best = max(cards, key=lambda c: c["spread_vs_reference"])
    return str(best["listing_id"])


def _saving_score(price: float | None, reference: float | None) -> float:
    if price is None or not reference:
        return 0.0
    saving_fraction = (reference - price) / reference
    return round(max(0.0, min(1.0, saving_fraction / _SAVING_FULL_CREDIT)), 4)
