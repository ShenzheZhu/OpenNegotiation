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

    def __init__(
        self,
        comparables: list[MarketComparable],
        *,
        mode: str = "clean",
        noise_fraction: float = 0.1,
        adversarial_multiplier: float = 1.25,
        stale_as_of: str | None = None,
    ) -> None:
        self.comparables = comparables
        if mode not in {"clean", "noisy", "stale", "adversarial", "failure"}:
            raise ValueError(f"unsupported market price mode: {mode}")
        self.mode = mode
        self.noise_fraction = noise_fraction
        self.adversarial_multiplier = adversarial_multiplier
        self.stale_as_of = stale_as_of

    @classmethod
    def from_json(
        cls,
        path: str | Path,
        *,
        mode: str = "clean",
        noise_fraction: float = 0.1,
        adversarial_multiplier: float = 1.25,
        stale_as_of: str | None = None,
    ) -> "MarketPriceTool":
        records = json.loads(Path(path).read_text())
        return cls(
            [MarketComparable.from_mapping(record) for record in records],
            mode=mode,
            noise_fraction=noise_fraction,
            adversarial_multiplier=adversarial_multiplier,
            stale_as_of=stale_as_of,
        )

    def call(
        self,
        arguments: Mapping[str, object],
        context: AgentContext | None,
    ) -> Mapping[str, object]:
        if self.mode == "failure":
            return {
                "ok": False,
                "mode": self.mode,
                "error": "configured market_price_search failure",
                "provenance": [],
            }
        if "query" in arguments:
            query = str(arguments["query"])
        elif context is not None:
            query = context.scenario.product.name
        else:
            raise ValueError("market_price_search requires a query when context is unavailable")
        condition = arguments.get("condition")
        limit = int(arguments.get("limit", 5))
        matches = self._search(query=query, condition=str(condition) if condition else None)[:limit]
        results = [
            self._result_for_match(match, index)
            for index, match in enumerate(matches)
        ]
        prices = [float(result["price"]) for result in results]
        return {
            "ok": True,
            "mode": self.mode,
            "query": query,
            "count": len(matches),
            "median_price": statistics.median(prices) if prices else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "provenance": [
                self._provenance_for_match(match)
                for match in matches
            ],
            "results": results,
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

    def _result_for_match(self, match: MarketComparable, index: int) -> Mapping[str, object]:
        price = self._price_for_match(match.price, index)
        result = {
            "title": match.title,
            "price": price,
            "condition": match.condition,
            "source": match.source,
            "original_price": match.price,
        }
        if self.mode == "stale":
            result["stale_as_of"] = self.stale_as_of or "unknown"
        return result

    def _price_for_match(self, price: float, index: int) -> float:
        if self.mode == "noisy":
            direction = 1 if index % 2 == 0 else -1
            return round(price * (1 + direction * self.noise_fraction), 2)
        if self.mode == "adversarial":
            return round(price * self.adversarial_multiplier, 2)
        return price

    def _provenance_for_match(self, match: MarketComparable) -> Mapping[str, object]:
        provenance = {
            "source": match.source,
            "title": match.title,
            "condition": match.condition,
            "mode": self.mode,
        }
        if self.mode == "stale":
            provenance["stale_as_of"] = self.stale_as_of or "unknown"
        return provenance
