"""Deterministic agents backed by marketplace strategy profiles."""

from __future__ import annotations

from dataclasses import dataclass

from opennego.agents.scripted import ScriptedSeller, ToolAwareBuyer
from opennego.learning import StrategyProfile
from opennego.schema import ActionType, AgentAction, AgentContext, Role, TranscriptEvent


def make_profile_agent_pair(
    *,
    profile: StrategyProfile,
    user_role: Role,
):
    """Create a deterministic user-vs-profile agent pair for sparring."""

    if profile.role == user_role:
        raise ValueError("opponent profile role must differ from user_role")
    if profile.role == Role.SELLER:
        return (
            ToolAwareBuyer(name="user_buyer"),
            ProfileBackedSeller(profile=profile),
        )
    return (
        ProfileBackedBuyer(profile=profile),
        ScriptedSeller(name="user_seller"),
    )


@dataclass
class ProfileBackedSeller:
    profile: StrategyProfile
    role: Role = Role.SELLER

    def __post_init__(self) -> None:
        if self.profile.role != Role.SELLER:
            raise ValueError("seller profile agent requires role=seller")

    @property
    def name(self) -> str:
        return f"npc_seller:{self.profile.id}"

    def act(self, context: AgentContext) -> AgentAction:
        events = tuple(context.transcript)
        buyer_offer = _latest_offer(events, Role.BUYER)
        floor = self._acceptance_floor(context)

        if buyer_offer and buyer_offer.offer:
            if buyer_offer.offer.price >= floor:
                return AgentAction.accept(
                    f"{self.profile.name} accepts at ${buyer_offer.offer.price:.2f}."
                )
            own_offer = _latest_offer(events, Role.SELLER)
            anchor = (
                own_offer.offer.price
                if own_offer and own_offer.offer
                else self._opening_price(context, floor)
            )
            counter = buyer_offer.offer.price + (
                anchor - buyer_offer.offer.price
            ) * self._concession_fraction()
            counter = max(floor, counter)
            return AgentAction.offer_price(
                round(counter, 2),
                f"{self.profile.archetype} counter: ${counter:.2f}.",
            )

        opening = self._opening_price(context, floor)
        return AgentAction.offer_price(
            round(opening, 2),
            f"{self.profile.archetype} opening: ${opening:.2f}.",
        )

    def _opening_price(self, context: AgentContext, floor: float) -> float:
        return max(floor, context.scenario.product.list_price * self._opening_markup())

    def _acceptance_floor(self, context: AgentContext) -> float:
        reservation = context.scenario.seller_reservation_price
        reference = context.scenario.product.market_reference
        if reference is None:
            return reservation
        if self.profile.archetype == "hardline_anchor":
            return max(reservation, reference.reference_price * 1.05)
        if self.profile.archetype == "evidence_asymmetry":
            return max(reservation, reference.reference_price * 0.98)
        return reservation

    def _opening_markup(self) -> float:
        if self.profile.archetype == "hardline_anchor":
            return 0.99
        if self.profile.archetype == "evidence_asymmetry":
            return 0.94
        if self.profile.archetype == "transaction_cost_pressure":
            return 0.90
        return 0.98

    def _concession_fraction(self) -> float:
        if self.profile.archetype == "hardline_anchor":
            return 0.25
        if self.profile.archetype == "evidence_asymmetry":
            return 0.35
        if self.profile.archetype == "transaction_cost_pressure":
            return 0.55
        return 0.45


@dataclass
class ProfileBackedBuyer:
    profile: StrategyProfile
    role: Role = Role.BUYER

    def __post_init__(self) -> None:
        if self.profile.role != Role.BUYER:
            raise ValueError("buyer profile agent requires role=buyer")

    @property
    def name(self) -> str:
        return f"npc_buyer:{self.profile.id}"

    def act(self, context: AgentContext) -> AgentAction:
        events = tuple(context.transcript)
        if self._should_call_market_tool(context, events):
            return AgentAction.tool(
                "market_price_search",
                {
                    "query": context.scenario.product.name,
                    "condition": context.scenario.product.condition,
                    "limit": 5,
                },
            )

        market_anchor = _latest_market_median(events)
        if market_anchor is None and context.scenario.product.market_reference is not None:
            market_anchor = context.scenario.product.market_reference.reference_price
        if market_anchor is None:
            market_anchor = context.scenario.product.list_price
        willingness = min(
            context.scenario.buyer_budget,
            market_anchor * self._willingness_multiplier(),
        )
        seller_offer = _latest_offer(events, Role.SELLER)

        if seller_offer and seller_offer.offer:
            if seller_offer.offer.price <= willingness:
                return AgentAction.accept(
                    f"{self.profile.name} accepts at ${seller_offer.offer.price:.2f}."
                )
            counter = min(
                willingness,
                seller_offer.offer.price * self._counter_fraction(),
            )
        else:
            counter = min(
                willingness,
                market_anchor * self._opening_discount(),
            )
        return AgentAction.offer_price(
            round(counter, 2),
            f"{self.profile.archetype} offer: ${counter:.2f}.",
        )

    def _should_call_market_tool(
        self,
        context: AgentContext,
        events: tuple[TranscriptEvent, ...],
    ) -> bool:
        if "market_price_search" not in context.available_tools:
            return False
        if "market_price_search" not in set(self.profile.allowed_tools):
            return False
        desired_calls = 2 if self.profile.archetype == "tool_overuse" else 1
        return _market_tool_call_count(events, Role.BUYER) < desired_calls

    def _opening_discount(self) -> float:
        if self.profile.archetype == "reservation_probe":
            return 0.72
        if self.profile.archetype == "tool_overuse":
            return 0.82
        return 0.80

    def _counter_fraction(self) -> float:
        if self.profile.archetype == "reservation_probe":
            return 0.82
        if self.profile.archetype == "tool_overuse":
            return 0.88
        return 0.85

    def _willingness_multiplier(self) -> float:
        if self.profile.archetype == "reservation_probe":
            return 0.92
        if self.profile.archetype == "tool_overuse":
            return 0.98
        return 0.95


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


def _market_tool_call_count(
    events: tuple[TranscriptEvent, ...],
    role: Role,
) -> int:
    return sum(
        1
        for event in events
        if event.role == role
        and event.action_type == ActionType.TOOL_CALL
        and event.tool_call is not None
        and event.tool_call.name == "market_price_search"
    )
