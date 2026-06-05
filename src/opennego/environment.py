"""Core negotiation environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .metrics import compute_metrics
from .ports import AgentPort, ToolPort, TransactionPort, TransactionRequest
from .schema import (
    ActionType,
    AgentAction,
    AgentContext,
    Role,
    RunResult,
    Scenario,
    TransactionOutcome,
    TranscriptEvent,
)


@dataclass(frozen=True)
class ToolRuntimeConfig:
    """Runtime access policy for one tool."""

    name: str
    roles: tuple[Role, ...] = (Role.BUYER, Role.SELLER)
    visibility: str = "private"
    fail_fast: bool = False

    def __post_init__(self) -> None:
        roles = tuple(Role(role) for role in self.roles)
        if not roles:
            raise ValueError("tool runtime config requires at least one role")
        object.__setattr__(self, "roles", roles)
        if self.visibility not in {"private", "public"}:
            raise ValueError("tool visibility must be 'private' or 'public'")


class NegotiationEnvironment:
    """Runs a two-party negotiation while preserving private tool traces."""

    def __init__(
        self,
        scenario: Scenario,
        buyer: AgentPort,
        seller: AgentPort,
        tools: tuple[ToolPort, ...] = (),
        tool_configs: tuple[ToolRuntimeConfig, ...] | None = None,
        transaction_simulator: TransactionPort | None = None,
    ) -> None:
        if buyer.role != Role.BUYER:
            raise ValueError("buyer agent must have role=Role.BUYER")
        if seller.role != Role.SELLER:
            raise ValueError("seller agent must have role=Role.SELLER")
        self.scenario = scenario
        self.buyer = buyer
        self.seller = seller
        self.tools = {tool.name: tool for tool in tools}
        self.tool_configs = self._normalize_tool_configs(tool_configs)
        self.transaction_simulator = transaction_simulator
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
                transaction = self._settle_transaction(
                    accepting_role=actor.role,
                    deal_price=deal_price,
                    next_turn=total_steps + 1,
                )
                return self._result(outcome, deal_price, public_turns, transaction)

            if action.type == ActionType.REJECT:
                return self._result("rejected", None, public_turns)

            actor = self._next_actor(actor)

        return self._result("timeout", None, public_turns)

    def _context_for(self, role: Role) -> AgentContext:
        visible_events = tuple(
            event
            for event in self.events
            if not event.private or event.role == role
        )
        private_state = {}
        if role == Role.BUYER:
            private_state["budget"] = self.scenario.buyer_budget
        else:
            private_state["reservation_price"] = self.scenario.seller_reservation_price
        return AgentContext(
            scenario=self.scenario,
            role=role,
            transcript=visible_events,
            available_tools=self._available_tools_for(role),
            private_state=private_state,
        )

    def _event_from_action(
        self,
        turn: int,
        actor: AgentPort,
        action: AgentAction,
        context: AgentContext,
    ) -> TranscriptEvent:
        if action.type == ActionType.TOOL_CALL:
            if action.tool_call is None:
                raise ValueError("tool_call action requires a ToolCall payload")
            result, private = self._execute_tool_call(actor, action, context)
            return TranscriptEvent(
                turn=turn,
                role=actor.role,
                actor=actor.name,
                action_type=action.type,
                content=action.content,
                tool_call=action.tool_call,
                tool_result=result,
                private=private,
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

    def _result(
        self,
        outcome: str,
        deal_price: float | None,
        completed_turns: int,
        transaction: TransactionOutcome | None = None,
    ) -> RunResult:
        metrics = compute_metrics(self.scenario, outcome, deal_price, self.events)
        return RunResult(
            scenario=self.scenario,
            events=tuple(self.events),
            outcome=outcome,
            deal_price=deal_price,
            completed_turns=completed_turns,
            metrics=metrics,
            transaction=transaction,
        )

    def _normalize_tool_configs(
        self,
        tool_configs: tuple[ToolRuntimeConfig, ...] | None,
    ) -> dict[str, ToolRuntimeConfig]:
        if tool_configs is None:
            return {
                name: ToolRuntimeConfig(name=name)
                for name in self.tools
            }
        configs = {config.name: config for config in tool_configs}
        missing_configs = set(self.tools) - set(configs)
        if missing_configs:
            raise ValueError(
                f"missing tool runtime config for: {sorted(missing_configs)}"
            )
        unknown_configs = set(configs) - set(self.tools)
        if unknown_configs:
            raise ValueError(
                "tool runtime config references unknown tools: "
                f"{sorted(unknown_configs)}"
            )
        return configs

    def _available_tools_for(self, role: Role) -> tuple[str, ...]:
        return tuple(
            name
            for name, config in self.tool_configs.items()
            if role in config.roles
        )

    def _execute_tool_call(
        self,
        actor: AgentPort,
        action: AgentAction,
        context: AgentContext,
    ) -> tuple[Mapping[str, object], bool]:
        assert action.tool_call is not None
        tool_name = action.tool_call.name
        config = self.tool_configs.get(tool_name)
        private = True if config is None else config.visibility == "private"
        if config is None or tool_name not in self.tools:
            return (
                self._tool_error_result(
                    tool_name=tool_name,
                    arguments=action.tool_call.arguments,
                    error=f"unknown tool: {tool_name}",
                    visibility="private",
                ),
                True,
            )
        if actor.role not in config.roles:
            return (
                self._tool_error_result(
                    tool_name=tool_name,
                    arguments=action.tool_call.arguments,
                    error=f"tool {tool_name} is not available to role {actor.role.value}",
                    visibility=config.visibility,
                ),
                private,
            )

        try:
            raw_result = self.tools[tool_name].call(action.tool_call.arguments, context)
        except Exception as exc:
            if config.fail_fast:
                raise
            return (
                self._tool_error_result(
                    tool_name=tool_name,
                    arguments=action.tool_call.arguments,
                    error=str(exc),
                    visibility=config.visibility,
                ),
                private,
            )
        return (
            self._tool_result_envelope(
                tool_name=tool_name,
                arguments=action.tool_call.arguments,
                visibility=config.visibility,
                raw_result=raw_result,
            ),
            private,
        )

    def _tool_result_envelope(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object],
        visibility: str,
        raw_result: Mapping[str, object],
    ) -> Mapping[str, object]:
        result = dict(raw_result)
        result.setdefault("ok", True)
        result["tool_name"] = tool_name
        result["arguments"] = dict(arguments)
        result["visibility"] = visibility
        result.setdefault("provenance", [])
        result.setdefault("latency_ms", None)
        result.setdefault("cost_usd", None)
        if result.get("ok") is False:
            result.setdefault("error", "tool call failed")
        return result

    def _tool_error_result(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object],
        error: str,
        visibility: str,
    ) -> Mapping[str, object]:
        return {
            "ok": False,
            "tool_name": tool_name,
            "arguments": dict(arguments),
            "visibility": visibility,
            "provenance": [],
            "latency_ms": None,
            "cost_usd": None,
            "error": error,
        }

    def _settle_transaction(
        self,
        *,
        accepting_role: Role,
        deal_price: float | None,
        next_turn: int,
    ) -> TransactionOutcome | None:
        if self.transaction_simulator is None or deal_price is None:
            return None
        transaction = self.transaction_simulator.settle(
            TransactionRequest(
                scenario=self.scenario,
                negotiated_price=deal_price,
                accepting_role=accepting_role.value,
            )
        )
        self.events.append(
            TranscriptEvent(
                turn=next_turn,
                role=Role.SYSTEM,
                actor="transaction_simulator",
                action_type=ActionType.TRANSACTION,
                content=transaction.status,
                transaction=transaction,
                private=False,
            )
        )
        return transaction
