"""Deterministic baseline agents."""

from __future__ import annotations

from dataclasses import dataclass

from opennego.schema import ActionType, AgentAction, AgentContext, Role, TranscriptEvent


def _latest_offer(events: tuple[TranscriptEvent, ...], role: Role | None = None) -> TranscriptEvent | None:
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


@dataclass
class ToolAwareBuyer:
    name: str = "tool_aware_buyer"
    role: Role = Role.BUYER
    market_discount: float = 0.95

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

        product = context.scenario.product
        market_anchor = _latest_market_median(events) or product.list_price
        max_willingness = min(context.scenario.buyer_budget, market_anchor * self.market_discount)
        seller_offer = _latest_offer(events, Role.SELLER)

        if seller_offer and seller_offer.offer and seller_offer.offer.price <= max_willingness:
            return AgentAction.accept(f"Accepted at ${seller_offer.offer.price:.2f}.")

        if seller_offer and seller_offer.offer:
            counter = min(max_willingness, seller_offer.offer.price * 0.9)
        else:
            counter = min(max_willingness, product.list_price * 0.8)
        return AgentAction.offer_price(round(counter, 2), f"My offer is ${counter:.2f}.")


@dataclass
class ScriptedSeller:
    name: str = "scripted_seller"
    role: Role = Role.SELLER
    opening_markup: float = 0.98
    concession_fraction: float = 0.45

    def act(self, context: AgentContext) -> AgentAction:
        events = tuple(context.transcript)
        product = context.scenario.product
        reservation = context.scenario.seller_reservation_price
        buyer_offer = _latest_offer(events, Role.BUYER)

        if buyer_offer and buyer_offer.offer:
            if buyer_offer.offer.price >= reservation:
                return AgentAction.accept(f"Accepted at ${buyer_offer.offer.price:.2f}.")
            own_offer = _latest_offer(events, Role.SELLER)
            anchor = own_offer.offer.price if own_offer and own_offer.offer else product.list_price
            counter = buyer_offer.offer.price + (anchor - buyer_offer.offer.price) * self.concession_fraction
            counter = max(reservation, counter)
            return AgentAction.offer_price(round(counter, 2), f"I can do ${counter:.2f}.")

        opening = max(reservation, product.list_price * self.opening_markup)
        return AgentAction.offer_price(round(opening, 2), f"I can offer it for ${opening:.2f}.")
