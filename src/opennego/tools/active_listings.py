"""Fixture-backed active-listing search tool.

Sold comps tell an agent what items actually traded for; active listings tell
it what the competition is asking right now. The spread between the two is
the negotiation room, and listing age signals seller motivation. This tool
exposes that surface from normalized fixture records.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from opennego.schema import AgentContext, parse_price


@dataclass(frozen=True)
class ActiveListing:
    query: str
    title: str
    asking_price: float
    condition: str = "unknown"
    listing_age_days: int | None = None
    shipping_cost: float | None = None
    seller_rating_band: str = "unknown"
    source: str = "unknown"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ActiveListing":
        age = data.get("listing_age_days")
        shipping = data.get("shipping_cost")
        return cls(
            query=str(data.get("query", data.get("title", ""))),
            title=str(data.get("title", "")),
            asking_price=parse_price(data["asking_price"]),
            condition=str(data.get("condition", "unknown")),
            listing_age_days=int(age) if age is not None else None,
            shipping_cost=parse_price(shipping) if shipping is not None else None,
            seller_rating_band=str(data.get("seller_rating_band", "unknown")),
            source=str(data.get("source", "unknown")),
        )


class ActiveListingTool:
    name = "active_listing_search"
    description = "Search fixture-backed active listings for a product."

    def __init__(self, listings: list[ActiveListing]) -> None:
        self.listings = listings

    @classmethod
    def from_json(cls, path: str | Path) -> "ActiveListingTool":
        records = json.loads(Path(path).read_text())
        return cls([ActiveListing.from_mapping(record) for record in records])

    def call(
        self,
        arguments: Mapping[str, object],
        context: AgentContext | None,
    ) -> Mapping[str, object]:
        if "query" in arguments:
            query = str(arguments["query"])
        elif context is not None:
            query = context.scenario.product.name
        else:
            raise ValueError(
                "active_listing_search requires a query when context is unavailable"
            )
        condition = arguments.get("condition")
        limit = int(arguments.get("limit", 5))
        matches = self._search(
            query=query,
            condition=str(condition) if condition else None,
        )[:limit]
        asking_prices = [listing.asking_price for listing in matches]
        ages = [
            listing.listing_age_days
            for listing in matches
            if listing.listing_age_days is not None
        ]
        return {
            "ok": True,
            "query": query,
            "count": len(matches),
            "median_asking_price": (
                statistics.median(asking_prices) if asking_prices else None
            ),
            "min_asking_price": min(asking_prices) if asking_prices else None,
            "max_asking_price": max(asking_prices) if asking_prices else None,
            "median_listing_age_days": statistics.median(ages) if ages else None,
            "provenance": [
                {"source": listing.source, "title": listing.title}
                for listing in matches
            ],
            "results": [self._result_for(listing) for listing in matches],
        }

    def _search(self, query: str, condition: str | None) -> list[ActiveListing]:
        query_tokens = {token.lower() for token in query.split() if len(token) > 2}

        def score(item: ActiveListing) -> tuple[int, bool]:
            haystack = f"{item.query} {item.title}".lower()
            token_score = sum(1 for token in query_tokens if token in haystack)
            condition_match = (
                condition is None or item.condition.lower() == condition.lower()
            )
            return token_score, condition_match

        filtered = [
            item for item in self.listings if score(item)[0] > 0 and score(item)[1]
        ]
        return sorted(filtered, key=lambda item: score(item)[0], reverse=True)

    def _result_for(self, listing: ActiveListing) -> Mapping[str, object]:
        return {
            "title": listing.title,
            "asking_price": listing.asking_price,
            "condition": listing.condition,
            "listing_age_days": listing.listing_age_days,
            "shipping_cost": listing.shipping_cost,
            "seller_rating_band": listing.seller_rating_band,
            "source": listing.source,
        }
