"""Fixture-backed market-comparable search tool."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from opennego.schema import AgentContext, parse_price


@dataclass(frozen=True)
class MarketComparable:
    query: str
    title: str
    price: float
    source: str
    condition: str = "unknown"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MarketComparable":
        return cls(
            query=str(data.get("query", data.get("title", ""))),
            title=str(data.get("title", "")),
            price=parse_price(data["price"]),
            source=str(data.get("source", "unknown")),
            condition=str(data.get("condition", "unknown")),
        )


class MarketPriceTool:
    name = "market_price_search"
    description = "Search fixture-backed comparable sales for a product."

    def __init__(self, comparables: list[MarketComparable]) -> None:
        self.comparables = comparables

    @classmethod
    def from_json(cls, path: str | Path) -> "MarketPriceTool":
        records = json.loads(Path(path).read_text())
        return cls([MarketComparable.from_mapping(record) for record in records])

    def call(self, arguments: Mapping[str, object], context: AgentContext | None) -> Mapping[str, object]:
        if "query" in arguments:
            query = str(arguments["query"])
        elif context is not None:
            query = context.scenario.product.name
        else:
            raise ValueError("market_price_search requires a query when context is unavailable")
        condition = arguments.get("condition")
        limit = int(arguments.get("limit", 5))
        matches = self._search(query=query, condition=str(condition) if condition else None)[:limit]
        prices = [match.price for match in matches]
        return {
            "ok": True,
            "query": query,
            "count": len(matches),
            "median_price": statistics.median(prices) if prices else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "results": [
                {
                    "title": match.title,
                    "price": match.price,
                    "condition": match.condition,
                    "source": match.source,
                }
                for match in matches
            ],
        }

    def _search(self, query: str, condition: str | None) -> list[MarketComparable]:
        query_tokens = {token.lower() for token in query.split() if len(token) > 2}

        def score(item: MarketComparable) -> tuple[int, bool]:
            haystack = f"{item.query} {item.title}".lower()
            token_score = sum(1 for token in query_tokens if token in haystack)
            condition_match = condition is None or item.condition.lower() == condition.lower()
            return token_score, condition_match

        filtered = [item for item in self.comparables if score(item)[0] > 0 and score(item)[1]]
        return sorted(filtered, key=lambda item: score(item)[0], reverse=True)
