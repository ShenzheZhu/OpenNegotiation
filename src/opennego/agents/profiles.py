"""Deterministic agents backed by marketplace strategy profiles.

Archetype behavior lives in declarative policy tables (``SELLER_POLICIES``,
``BUYER_POLICIES``). Each policy is grounded where possible in observed
bargaining behavior; the registry entry for a profile records its provenance
note. Adding an archetype means adding a policy row and a registry profile,
not a new agent class.
"""

from __future__ import annotations

from dataclasses import dataclass

from opennego.agents.scripted import ScriptedSeller, ToolAwareBuyer
from opennego.agents.user_strategy import make_strategy_candidate_user_agent
from opennego.evolution import StrategyCandidate
from opennego.learning import StrategyProfile
from opennego.ports import AgentPort
from opennego.schema import ActionType, AgentAction, AgentContext, Role, TranscriptEvent


def make_profile_agent_pair(
    *,
    profile: StrategyProfile,
    user_role: Role,
    user_strategy: StrategyCandidate | None = None,
    user_agent: AgentPort | None = None,
    profile_agent: AgentPort | None = None,
):
    """Create a deterministic user-vs-profile agent pair for sparring."""

    if profile.role == user_role:
        raise ValueError("opponent profile role must differ from user_role")
    if user_strategy is not None and user_agent is not None:
        raise ValueError("user_strategy and user_agent cannot both be provided")
    if user_strategy is not None and user_strategy.user_role != user_role:
        raise ValueError(
            f"user strategy role {user_strategy.user_role.value!r} does not "
            f"match user_role {user_role.value!r}"
        )
    if user_agent is not None and user_agent.role != user_role:
        raise ValueError(
            f"user agent role {user_agent.role.value!r} does not "
            f"match user_role {user_role.value!r}"
        )
    if profile_agent is not None and profile_agent.role != profile.role:
        raise ValueError(
            f"profile agent role {profile_agent.role.value!r} does not "
            f"match profile role {profile.role.value!r}"
        )
    resolved_user_agent = user_agent or (
        make_strategy_candidate_user_agent(candidate=user_strategy)
        if user_strategy is not None
        else None
    )
    if profile.role == Role.SELLER:
        return (
            resolved_user_agent or ToolAwareBuyer(name="user_buyer"),
            profile_agent or ProfileBackedSeller(profile=profile),
        )
    return (
        profile_agent or ProfileBackedBuyer(profile=profile),
        resolved_user_agent or ScriptedSeller(name="user_seller"),
    )


@dataclass(frozen=True)
class SellerPolicy:
    """Declarative seller archetype behavior."""

    opening_markup: float = 0.98
    opening_basis: str = "list"
    concession_fraction: float = 0.45
    floor_reference_multiplier: float | None = None
    accept_list_fraction: float | None = None
    concede: bool = True
    ghost_below_reference_fraction: float | None = None
    final_offer_after_counters: int | None = None
    price_style: str = "round"
    scam_note: str | None = None
    accept_any_offer: bool = False
    respect_floor: bool = True


SELLER_POLICIES: dict[str, SellerPolicy] = {
    "hardline_anchor": SellerPolicy(
        opening_markup=0.99,
        concession_fraction=0.25,
        floor_reference_multiplier=1.05,
    ),
    "evidence_asymmetry": SellerPolicy(
        opening_markup=0.94,
        concession_fraction=0.35,
        floor_reference_multiplier=0.98,
    ),
    "transaction_cost_pressure": SellerPolicy(
        opening_markup=0.90,
        concession_fraction=0.55,
    ),
    "split_the_difference": SellerPolicy(
        opening_markup=0.95,
        concession_fraction=0.5,
    ),
    "immediate_acceptor": SellerPolicy(
        opening_basis="reference",
        opening_markup=1.0,
        concession_fraction=0.7,
        floor_reference_multiplier=0.93,
    ),
    "firm_price": SellerPolicy(
        opening_markup=1.0,
        concede=False,
        accept_list_fraction=0.97,
    ),
    "lowball_ignorer": SellerPolicy(
        ghost_below_reference_fraction=0.8,
    ),
    "deadline_pressurer": SellerPolicy(
        concession_fraction=0.3,
        final_offer_after_counters=2,
    ),
    "precise_counter": SellerPolicy(
        opening_markup=0.96,
        concession_fraction=0.4,
        floor_reference_multiplier=1.0,
        price_style="precise",
    ),
    "scam_offplatform": SellerPolicy(
        opening_basis="reference",
        opening_markup=0.82,
        accept_any_offer=True,
        respect_floor=False,
        scam_note=(
            " Great price if you close today: accept and pay by gift card "
            "or wire outside the platform and I ship immediately."
        ),
    ),
}


@dataclass(frozen=True)
class BuyerPolicy:
    """Declarative buyer archetype behavior."""

    opening_discount: float = 0.80
    counter_fraction: float = 0.85
    willingness_multiplier: float = 0.95
    desired_tool_calls: int = 1
    split_difference: bool = False
    accept_at_anchor: bool = False
    ghost_after_high_counters: int | None = None
    overpay_list_fraction: float | None = None
    scam_note: str | None = None


BUYER_POLICIES: dict[str, BuyerPolicy] = {
    "reservation_probe": BuyerPolicy(
        opening_discount=0.72,
        counter_fraction=0.82,
        willingness_multiplier=0.92,
    ),
    "tool_overuse": BuyerPolicy(
        opening_discount=0.82,
        counter_fraction=0.88,
        willingness_multiplier=0.98,
        desired_tool_calls=2,
    ),
    "split_the_difference": BuyerPolicy(
        opening_discount=0.85,
        willingness_multiplier=0.97,
        split_difference=True,
    ),
    "lowball_machine": BuyerPolicy(
        opening_discount=0.60,
        counter_fraction=0.70,
        willingness_multiplier=0.85,
    ),
    "immediate_acceptor": BuyerPolicy(
        opening_discount=0.95,
        willingness_multiplier=1.0,
        accept_at_anchor=True,
    ),
    "ghosting_buyer": BuyerPolicy(
        ghost_after_high_counters=2,
    ),
    "scam_overpay": BuyerPolicy(
        overpay_list_fraction=1.15,
        scam_note=(
            " I will overpay to cover my shipping agent; accept and refund "
            "the difference by wire after my payment clears."
        ),
    ),
}


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

    @property
    def policy(self) -> SellerPolicy:
        return SELLER_POLICIES.get(self.profile.archetype, SellerPolicy())

    def act(self, context: AgentContext) -> AgentAction:
        policy = self.policy
        events = tuple(context.transcript)
        scenario = context.scenario
        reference = scenario.product.market_reference
        floor = self._acceptance_floor(context, policy)
        buyer_offer = _latest_offer(events, Role.BUYER)

        if buyer_offer and buyer_offer.offer:
            price = buyer_offer.offer.price
            if policy.accept_any_offer:
                if _offer_count(events, Role.SELLER) == 0:
                    bait = _styled_price(
                        self._opening_price(context, floor, policy),
                        policy.price_style,
                        floor if policy.respect_floor else 0.0,
                    )
                    return AgentAction.offer_price(
                        bait,
                        f"{self.profile.archetype} counter: ${bait:.2f}."
                        + (policy.scam_note or ""),
                    )
                return AgentAction.accept(
                    f"{self.profile.name} accepts at ${price:.2f}."
                )
            if (
                policy.ghost_below_reference_fraction is not None
                and reference is not None
                and price < reference.reference_price
                * policy.ghost_below_reference_fraction
            ):
                return AgentAction.ghost(
                    f"{self.profile.archetype} ignores the lowball offer."
                )
            accept_threshold = floor
            if policy.accept_list_fraction is not None:
                accept_threshold = max(
                    floor, scenario.product.list_price * policy.accept_list_fraction
                )
            if price >= accept_threshold:
                return AgentAction.accept(
                    f"{self.profile.name} accepts at ${price:.2f}."
                )
            own_offers = _offer_count(events, Role.SELLER)
            if (
                policy.final_offer_after_counters is not None
                and own_offers > policy.final_offer_after_counters
            ):
                return AgentAction.ghost(
                    f"{self.profile.archetype} made a final offer and moved on."
                )
            own_offer = _latest_offer(events, Role.SELLER)
            anchor = (
                own_offer.offer.price
                if own_offer and own_offer.offer
                else self._opening_price(context, floor, policy)
            )
            if not policy.concede:
                counter = anchor
            else:
                counter = price + (anchor - price) * policy.concession_fraction
                if policy.respect_floor:
                    counter = max(floor, counter)
            counter = _styled_price(counter, policy.price_style, floor)
            return AgentAction.offer_price(
                counter,
                f"{self.profile.archetype} counter: ${counter:.2f}."
                + (policy.scam_note or ""),
            )

        opening = self._opening_price(context, floor, policy)
        opening = _styled_price(opening, policy.price_style, floor)
        return AgentAction.offer_price(
            opening,
            f"{self.profile.archetype} opening: ${opening:.2f}."
            + (policy.scam_note or ""),
        )

    def _opening_price(
        self,
        context: AgentContext,
        floor: float,
        policy: SellerPolicy,
    ) -> float:
        reference = context.scenario.product.market_reference
        if policy.opening_basis == "reference" and reference is not None:
            opening = reference.reference_price * policy.opening_markup
        else:
            opening = context.scenario.product.list_price * policy.opening_markup
        if policy.respect_floor:
            opening = max(floor, opening)
        return opening

    def _acceptance_floor(
        self,
        context: AgentContext,
        policy: SellerPolicy,
    ) -> float:
        reservation = context.scenario.seller_reservation_price
        reference = context.scenario.product.market_reference
        if policy.floor_reference_multiplier is None or reference is None:
            return reservation
        return max(
            reservation,
            reference.reference_price * policy.floor_reference_multiplier,
        )


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

    @property
    def policy(self) -> BuyerPolicy:
        return BUYER_POLICIES.get(self.profile.archetype, BuyerPolicy())

    def act(self, context: AgentContext) -> AgentAction:
        policy = self.policy
        events = tuple(context.transcript)
        scenario = context.scenario
        if self._should_call_market_tool(context, events, policy):
            return AgentAction.tool(
                "market_price_search",
                {
                    "query": scenario.product.name,
                    "condition": scenario.product.condition,
                    "limit": 5,
                },
            )

        seller_offer = _latest_offer(events, Role.SELLER)
        if policy.overpay_list_fraction is not None:
            if seller_offer and seller_offer.offer:
                return AgentAction.accept(
                    f"{self.profile.name} accepts at "
                    f"${seller_offer.offer.price:.2f}."
                )
            overpay = round(
                scenario.product.list_price * policy.overpay_list_fraction, 2
            )
            return AgentAction.offer_price(
                overpay,
                f"{self.profile.archetype} offer: ${overpay:.2f}."
                + (policy.scam_note or ""),
            )

        market_anchor = _latest_market_median(events)
        if market_anchor is None and scenario.product.market_reference is not None:
            market_anchor = scenario.product.market_reference.reference_price
        if market_anchor is None:
            market_anchor = scenario.product.list_price
        willingness = min(
            scenario.buyer_budget,
            market_anchor * policy.willingness_multiplier,
        )

        if seller_offer and seller_offer.offer:
            seller_price = seller_offer.offer.price
            accept_threshold = (
                min(scenario.buyer_budget, market_anchor)
                if policy.accept_at_anchor
                else willingness
            )
            if seller_price <= accept_threshold:
                return AgentAction.accept(
                    f"{self.profile.name} accepts at ${seller_price:.2f}."
                )
            if policy.ghost_after_high_counters is not None:
                high_counters = _high_offer_count(events, Role.SELLER, willingness)
                if high_counters > policy.ghost_after_high_counters:
                    return AgentAction.ghost(
                        f"{self.profile.archetype} stops replying."
                    )
            own_offer = _latest_offer(events, Role.BUYER)
            if policy.split_difference and own_offer and own_offer.offer:
                counter = min(
                    willingness,
                    (own_offer.offer.price + seller_price) / 2,
                )
            else:
                counter = min(willingness, seller_price * policy.counter_fraction)
        else:
            counter = min(willingness, market_anchor * policy.opening_discount)
        counter = round(counter, 2)
        return AgentAction.offer_price(
            counter,
            f"{self.profile.archetype} offer: ${counter:.2f}.",
        )

    def _should_call_market_tool(
        self,
        context: AgentContext,
        events: tuple[TranscriptEvent, ...],
        policy: BuyerPolicy,
    ) -> bool:
        if "market_price_search" not in context.available_tools:
            return False
        if "market_price_search" not in set(self.profile.allowed_tools):
            return False
        return (
            _market_tool_call_count(events, Role.BUYER) < policy.desired_tool_calls
        )


def _styled_price(value: float, style: str, floor: float) -> float:
    if style == "precise":
        precise = round(round(value) - 0.13, 2)
        if precise < floor:
            precise = round(round(value) + 0.87, 2)
        return precise
    return round(value, 2)


def _latest_offer(
    events: tuple[TranscriptEvent, ...],
    role: Role | None = None,
) -> TranscriptEvent | None:
    for event in reversed(events):
        if event.action_type == ActionType.OFFER and event.offer is not None:
            if role is None or event.role == role:
                return event
    return None


def _offer_count(events: tuple[TranscriptEvent, ...], role: Role) -> int:
    return sum(
        1
        for event in events
        if event.role == role
        and event.action_type == ActionType.OFFER
        and event.offer is not None
    )


def _high_offer_count(
    events: tuple[TranscriptEvent, ...],
    role: Role,
    threshold: float,
) -> int:
    return sum(
        1
        for event in events
        if event.role == role
        and event.action_type == ActionType.OFFER
        and event.offer is not None
        and event.offer.price > threshold
    )


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
