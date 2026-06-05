"""Deterministic user agents that consume strategy candidate artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from opennego.evolution import StrategyCandidate
from opennego.schema import ActionType, AgentAction, AgentContext, Role, TranscriptEvent


def make_strategy_candidate_user_agent(
    *,
    candidate: StrategyCandidate,
):
    """Create the deterministic user agent represented by a strategy candidate."""

    if candidate.user_role == Role.BUYER:
        return StrategyCandidateBuyer(candidate=candidate)
    if candidate.user_role == Role.SELLER:
        return StrategyCandidateSeller(candidate=candidate)
    raise ValueError(f"unsupported strategy candidate role: {candidate.user_role.value}")


@dataclass
class StrategyCandidateBuyer:
    candidate: StrategyCandidate
    role: Role = Role.BUYER
    market_discount: float = 0.95
    market_cap_multiplier: float = 1.05

    def __post_init__(self) -> None:
        if self.candidate.user_role != Role.BUYER:
            raise ValueError("buyer strategy candidate requires role=buyer")

    @property
    def name(self) -> str:
        return f"user_buyer:{self.candidate.candidate_id}"

    @property
    def strategy_candidate_id(self) -> str:
        return self.candidate.candidate_id

    @property
    def applied_lesson_ids(self) -> tuple[str, ...]:
        return self.candidate.applied_lesson_ids

    @property
    def parent_strategy_id(self) -> str:
        return self.candidate.parent_strategy_id

    def act(self, context: AgentContext) -> AgentAction:
        events = tuple(context.transcript)
        if "market_price_search" in context.available_tools and not _has_market_search(events):
            return AgentAction.tool(
                "market_price_search",
                {
                    "query": context.scenario.product.name,
                    "condition": context.scenario.product.condition,
                    "limit": 5,
                },
            )

        max_willingness = self._max_willingness(context, events)
        seller_offer = _latest_offer(events, Role.SELLER)
        if seller_offer and seller_offer.offer:
            if seller_offer.offer.price <= max_willingness:
                return AgentAction.accept(
                    f"Accepted at ${seller_offer.offer.price:.2f}."
                )
            counter = min(max_willingness, seller_offer.offer.price * 0.9)
        else:
            counter = self._opening_offer(context, events, max_willingness)
        return AgentAction.offer_price(round(counter, 2), f"My offer is ${counter:.2f}.")

    def _max_willingness(
        self,
        context: AgentContext,
        events: tuple[TranscriptEvent, ...],
    ) -> float:
        product = context.scenario.product
        market_median = _latest_market_median(events)
        if market_median is not None:
            anchor = market_median
            multiplier = self.market_cap_multiplier
        elif self._has_price_discipline() and product.market_reference is not None:
            anchor = product.market_reference.reference_price
            multiplier = self.market_cap_multiplier
        else:
            anchor = product.list_price
            multiplier = self.market_discount
        return min(context.scenario.buyer_budget, anchor * multiplier)

    def _opening_offer(
        self,
        context: AgentContext,
        events: tuple[TranscriptEvent, ...],
        max_willingness: float,
    ) -> float:
        product = context.scenario.product
        market_median = _latest_market_median(events)
        if market_median is not None:
            anchor = market_median
            multiplier = self.market_discount
        elif self._has_price_discipline() and product.market_reference is not None:
            anchor = product.market_reference.reference_price
            multiplier = self.market_discount
        else:
            anchor = product.list_price
            multiplier = 0.8
        return min(max_willingness, anchor * multiplier)

    def _has_price_discipline(self) -> bool:
        return any(
            lesson_id in self.candidate.applied_lesson_ids
            for lesson_id in ("buyer_overpaid_market", "missed_market_tool")
        )


@dataclass
class StrategyCandidateSeller:
    candidate: StrategyCandidate
    role: Role = Role.SELLER
    opening_markup: float = 0.98
    concession_fraction: float = 0.35
    market_floor_multiplier: float = 0.9

    def __post_init__(self) -> None:
        if self.candidate.user_role != Role.SELLER:
            raise ValueError("seller strategy candidate requires role=seller")

    @property
    def name(self) -> str:
        return f"user_seller:{self.candidate.candidate_id}"

    @property
    def strategy_candidate_id(self) -> str:
        return self.candidate.candidate_id

    @property
    def applied_lesson_ids(self) -> tuple[str, ...]:
        return self.candidate.applied_lesson_ids

    @property
    def parent_strategy_id(self) -> str:
        return self.candidate.parent_strategy_id

    def act(self, context: AgentContext) -> AgentAction:
        events = tuple(context.transcript)
        floor = self._floor(context)
        buyer_offer = _latest_offer(events, Role.BUYER)

        if buyer_offer and buyer_offer.offer:
            if buyer_offer.offer.price >= floor:
                return AgentAction.accept(
                    f"Accepted at ${buyer_offer.offer.price:.2f}."
                )
            own_offer = _latest_offer(events, Role.SELLER)
            anchor = own_offer.offer.price if own_offer and own_offer.offer else self._opening(context, floor)
            counter = buyer_offer.offer.price + (
                anchor - buyer_offer.offer.price
            ) * self.concession_fraction
            counter = max(floor, counter)
            return AgentAction.offer_price(round(counter, 2), f"I can do ${counter:.2f}.")

        opening = self._opening(context, floor)
        return AgentAction.offer_price(
            round(opening, 2),
            f"I can offer it for ${opening:.2f}.",
        )

    def _floor(self, context: AgentContext) -> float:
        floor = context.scenario.seller_reservation_price
        reference = context.scenario.product.market_reference
        if self._has_price_floor() and reference is not None:
            floor = max(floor, reference.reference_price * self.market_floor_multiplier)
        return floor

    def _opening(self, context: AgentContext, floor: float) -> float:
        return max(floor, context.scenario.product.list_price * self.opening_markup)

    def _has_price_floor(self) -> bool:
        return any(
            lesson_id in self.candidate.applied_lesson_ids
            for lesson_id in ("seller_below_reservation", "seller_undersold_market")
        )


def _latest_offer(
    events: tuple[TranscriptEvent, ...],
    role: Role | None = None,
) -> TranscriptEvent | None:
    for event in reversed(events):
        if event.action_type == ActionType.OFFER and event.offer is not None:
            if role is None or event.role == role:
                return event
    return None


def _latest_market_median(events: tuple[TranscriptEvent, ...]) -> float | None:
    for event in reversed(events):
        if event.action_type != ActionType.TOOL_CALL or not event.tool_result:
            continue
        median_price = event.tool_result.get("median_price")
        if isinstance(median_price, (int, float)):
            return float(median_price)
    return None


def _has_market_search(events: tuple[TranscriptEvent, ...]) -> bool:
    return any(
        event.action_type == ActionType.TOOL_CALL
        and event.tool_call is not None
        and event.tool_call.name == "market_price_search"
        for event in events
    )
