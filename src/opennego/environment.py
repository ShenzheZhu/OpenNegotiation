"""Core negotiation environment."""

from __future__ import annotations

from typing import Mapping

from .metrics import compute_metrics
from .ports import AgentPort, ToolPort
from .schema import (
    ActionType,
    AgentAction,
    AgentContext,
    Role,
    RunResult,
    Scenario,
    TranscriptEvent,
)


class NegotiationEnvironment:
    """Runs a two-party negotiation while preserving private tool traces."""

    def __init__(
        self,
        scenario: Scenario,
        buyer: AgentPort,
        seller: AgentPort,
        tools: tuple[ToolPort, ...] = (),
    ) -> None:
        if buyer.role != Role.BUYER:
            raise ValueError("buyer agent must have role=Role.BUYER")
        if seller.role != Role.SELLER:
            raise ValueError("seller agent must have role=Role.SELLER")
        self.scenario = scenario
        self.buyer = buyer
        self.seller = seller
        self.tools = {tool.name: tool for tool in tools}
        self.events: list[TranscriptEvent] = []
        self._latest_offer_role: Role | None = None
        self._latest_offer_price: float | None = None

    def run(self) -> RunResult:
        actor: AgentPort = self.buyer
        public_turns = 0
        total_steps = 0
        max_total_steps = self.scenario.max_turns * 4

        while public_turns < self.scenario.max_turns and total_steps < max_total_steps:
            total_steps += 1
            context = self._context_for(actor.role)
            action = actor.act(context)
            event = self._event_from_action(total_steps, actor, action, context)
            self.events.append(event)

            if action.type == ActionType.TOOL_CALL:
                continue

            public_turns += 1
            if action.type == ActionType.OFFER and action.offer is not None:
                self._latest_offer_role = actor.role
                self._latest_offer_price = action.offer.price
                actor = self._next_actor(actor)
                continue

            if action.type == ActionType.ACCEPT:
                outcome, deal_price = self._accept_outcome(actor.role)
                return self._result(outcome, deal_price, public_turns)

            if action.type == ActionType.REJECT:
                return self._result("rejected", None, public_turns)

            actor = self._next_actor(actor)

        return self._result("timeout", None, public_turns)

    def _context_for(self, role: Role) -> AgentContext:
        visible_events = tuple(event for event in self.events if not event.private or event.role == role)
        private_state = {}
        if role == Role.BUYER:
            private_state["budget"] = self.scenario.buyer_budget
        else:
            private_state["reservation_price"] = self.scenario.seller_reservation_price
        return AgentContext(
            scenario=self.scenario,
            role=role,
            transcript=visible_events,
            available_tools=tuple(self.tools.keys()),
            private_state=private_state,
        )

    def _event_from_action(
        self,
        turn: int,
        actor: NegotiationAgent,
        action: AgentAction,
        context: AgentContext,
    ) -> TranscriptEvent:
        if action.type == ActionType.TOOL_CALL:
            if action.tool_call is None:
                raise ValueError("tool_call action requires a ToolCall payload")
            tool = self.tools.get(action.tool_call.name)
            if tool is None:
                result: Mapping[str, object] = {
                    "ok": False,
                    "error": f"unknown tool: {action.tool_call.name}",
                }
            else:
                result = tool.call(action.tool_call.arguments, context)
            return TranscriptEvent(
                turn=turn,
                role=actor.role,
                actor=actor.name,
                action_type=action.type,
                content=action.content,
                tool_call=action.tool_call,
                tool_result=result,
                private=True,
            )

        return TranscriptEvent(
            turn=turn,
            role=actor.role,
            actor=actor.name,
            action_type=action.type,
            content=action.content,
            offer=action.offer,
            private=False,
        )

    def _accept_outcome(self, accepting_role: Role) -> tuple[str, float | None]:
        if self._latest_offer_role is None or self._latest_offer_price is None:
            return "invalid_accept", None
        if self._latest_offer_role == accepting_role:
            return "invalid_accept", None
        return "deal", self._latest_offer_price

    def _next_actor(self, actor: AgentPort) -> AgentPort:
        return self.seller if actor.role == Role.BUYER else self.buyer

    def _result(self, outcome: str, deal_price: float | None, completed_turns: int) -> RunResult:
        metrics = compute_metrics(self.scenario, outcome, deal_price, self.events)
        return RunResult(
            scenario=self.scenario,
            events=tuple(self.events),
            outcome=outcome,
            deal_price=deal_price,
            completed_turns=completed_turns,
            metrics=metrics,
        )
