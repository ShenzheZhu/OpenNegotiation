"""Market runtime: a listings pool with a lifecycle and discovery.

See ``docs/design/market.md``. ``MarketState`` is the world the sandbox runs
in: a pool of listings built from real-market product fixtures, advanced by a
deterministic ``step`` (age, price-drop on stale listings, expire/relist), and
queried through ``discover``. The concurrency scheduler (#181) negotiates over
this state; here we only build and evolve the world.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.schema import Product, parse_price

MARKET_STATE_SCHEMA_VERSION = "opennego.market_state.v1"

# A listing past this age (periods) without selling expires; stale listings
# past the drop threshold cut price toward the sold-comps reference.
DEFAULT_MAX_AGE = 8
DEFAULT_DROP_AFTER = 3
DEFAULT_DROP_FRACTION = 0.04
DEFAULT_RELIST_FRACTION = 0.5


class MarketError(ValueError):
    """Raised when a market cannot be built or advanced."""


@dataclass(frozen=True)
class Listing:
    listing_id: str
    product_id: str
    title: str
    category: str
    condition: str
    asking_price: float
    reference_price: float
    seller_participant_id: str
    age_periods: int = 0
    status: str = "active"  # active | expired | sold

    def card(self) -> Mapping[str, Any]:
        """Discovery-visible fields, mirroring the active-listing tool shape."""

        spread = round(self.reference_price - self.asking_price, 2)
        return {
            "listing_id": self.listing_id,
            "product_id": self.product_id,
            "title": self.title,
            "category": self.category,
            "condition": self.condition,
            "asking_price": self.asking_price,
            "reference_price": self.reference_price,
            "spread_vs_reference": spread,
            "age_periods": self.age_periods,
            "seller_participant_id": self.seller_participant_id,
        }


@dataclass(frozen=True)
class MarketState:
    schema_version: str
    seed: int
    period: int
    listings: tuple[Listing, ...]
    settings: Mapping[str, Any] = field(default_factory=dict)

    def active(self) -> tuple[Listing, ...]:
        return tuple(l for l in self.listings if l.status == "active")

    def discover(
        self,
        *,
        category: str | None = None,
        max_price: float | None = None,
        limit: int = 10,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return active listing cards, best apparent deal first."""

        matches = [
            listing
            for listing in self.active()
            if (category is None or listing.category == category)
            and (max_price is None or listing.asking_price <= max_price)
        ]
        matches.sort(key=lambda l: l.asking_price - l.reference_price)
        return tuple(listing.card() for listing in matches[:limit])


def build_market(
    products_file: str | Path,
    *,
    seed: int = 13,
    listings_per_product: int = 2,
    max_age: int = DEFAULT_MAX_AGE,
    drop_after: int = DEFAULT_DROP_AFTER,
) -> MarketState:
    """Build a deterministic listings pool from a products fixture."""

    records = json.loads(Path(products_file).read_text())
    if not isinstance(records, list) or not records:
        raise MarketError(f"{products_file}: expected a non-empty product list")
    if listings_per_product < 1:
        raise MarketError("listings_per_product: expected at least one")

    rng = random.Random(f"market:{seed}")
    listings: list[Listing] = []
    for record in records:
        product = Product.from_mapping(record)
        reference = _reference_price(product)
        category = str(record.get("category", "uncategorized"))
        for index in range(listings_per_product):
            # Sellers price from clearly-over-market to near-reference.
            asking = round(reference * rng.uniform(0.98, 1.28), 2)
            listings.append(
                Listing(
                    listing_id=f"{product.id}__{index}",
                    product_id=product.id,
                    title=product.name,
                    category=category,
                    condition=product.condition,
                    asking_price=asking,
                    reference_price=reference,
                    seller_participant_id=f"seller::{product.id}__{index}",
                    age_periods=rng.randint(0, 2),
                    status="active",
                )
            )
    return MarketState(
        schema_version=MARKET_STATE_SCHEMA_VERSION,
        seed=seed,
        period=0,
        listings=tuple(listings),
        settings={
            "max_age": max_age,
            "drop_after": drop_after,
            "drop_fraction": DEFAULT_DROP_FRACTION,
            "relist_fraction": DEFAULT_RELIST_FRACTION,
            "listings_per_product": listings_per_product,
        },
    )


def step_market(state: MarketState) -> MarketState:
    """Advance the world one period: age, drop stale prices, expire/relist.

    Deterministic in the state's seed and current period, so a market replays
    identically. Expired listings relist (a fraction) at a refreshed price to
    keep liquidity.
    """

    settings = state.settings
    max_age = int(settings.get("max_age", DEFAULT_MAX_AGE))
    drop_after = int(settings.get("drop_after", DEFAULT_DROP_AFTER))
    drop_fraction = float(settings.get("drop_fraction", DEFAULT_DROP_FRACTION))
    relist_fraction = float(settings.get("relist_fraction", DEFAULT_RELIST_FRACTION))
    next_period = state.period + 1
    rng = random.Random(f"market:{state.seed}:step:{next_period}")

    updated: list[Listing] = []
    for listing in state.listings:
        if listing.status != "active":
            updated.append(listing)
            continue
        age = listing.age_periods + 1
        asking = listing.asking_price
        if age >= drop_after and asking > listing.reference_price:
            # Stale and over-market: cut toward the reference.
            asking = round(
                max(listing.reference_price, asking * (1 - drop_fraction)), 2
            )
        if age > max_age:
            updated.append(replace(listing, status="expired", age_periods=age))
            if rng.random() < relist_fraction:
                updated.append(
                    replace(
                        listing,
                        listing_id=f"{listing.listing_id}__r{next_period}",
                        asking_price=round(listing.reference_price * 1.15, 2),
                        age_periods=0,
                        status="active",
                    )
                )
        else:
            updated.append(replace(listing, asking_price=asking, age_periods=age))

    return MarketState(
        schema_version=MARKET_STATE_SCHEMA_VERSION,
        seed=state.seed,
        period=next_period,
        listings=tuple(updated),
        settings=settings,
    )


def mark_sold(state: MarketState, listing_id: str) -> MarketState:
    """Mark a listing sold (used by the scheduler on clearing)."""

    found = False
    updated = []
    for listing in state.listings:
        if listing.listing_id == listing_id and listing.status == "active":
            updated.append(replace(listing, status="sold"))
            found = True
        else:
            updated.append(listing)
    if not found:
        raise MarketError(f"no active listing to mark sold: {listing_id}")
    return replace(state, listings=tuple(updated))


def _reference_price(product: Product) -> float:
    if product.market_reference is not None:
        return product.market_reference.reference_price
    return product.list_price


def market_state_from_mapping(data: Mapping[str, Any]) -> MarketState:
    if data.get("schema_version") != MARKET_STATE_SCHEMA_VERSION:
        raise MarketError(
            "schema_version: expected "
            f"{MARKET_STATE_SCHEMA_VERSION!r}, got {data.get('schema_version')!r}"
        )
    listings = tuple(_listing_from_mapping(item) for item in data.get("listings", ()))
    return MarketState(
        schema_version=MARKET_STATE_SCHEMA_VERSION,
        seed=int(data.get("seed", 0)),
        period=int(data.get("period", 0)),
        listings=listings,
        settings=dict(data.get("settings", {})),
    )


def _listing_from_mapping(data: Mapping[str, Any]) -> Listing:
    return Listing(
        listing_id=str(data["listing_id"]),
        product_id=str(data.get("product_id", "")),
        title=str(data.get("title", "")),
        category=str(data.get("category", "uncategorized")),
        condition=str(data.get("condition", "unknown")),
        asking_price=parse_price(data["asking_price"]),
        reference_price=parse_price(data["reference_price"]),
        seller_participant_id=str(data.get("seller_participant_id", "")),
        age_periods=int(data.get("age_periods", 0)),
        status=str(data.get("status", "active")),
    )
