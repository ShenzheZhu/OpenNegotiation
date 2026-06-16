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

RULES_ACTOR = "negotiation_rules"


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


@dataclass(frozen=True)
class NegotiationRules:
    """Optional market time-structure rules.

    All fields default to "off", so an environment without rules behaves
    exactly like the classic unlimited-counter, never-expiring protocol.

    - ``offer_expiry_turns``: a standing offer lapses after this many public
      turns; an expiry of 1 means the counterpart must respond immediately.
    - ``max_offers_per_side``: cap on offers (including counters) per role.
      An offer beyond the cap ends the run as ``invalid_offer``.
    - ``turn_delay_cost``: bookkeeping cost per public turn, reported in
      metrics as ``turn_delay_cost_total``.
    """

    offer_expiry_turns: int | None = None
    max_offers_per_side: int | None = None
    turn_delay_cost: float = 0.0

    def __post_init__(self) -> None:
        if self.offer_expiry_turns is not None and self.offer_expiry_turns <= 0:
            raise ValueError("offer_expiry_turns must be positive when set")
        if self.max_offers_per_side is not None and self.max_offers_per_side <= 0:
            raise ValueError("max_offers_per_side must be positive when set")
        if self.turn_delay_cost < 0:
            raise ValueError("turn_delay_cost must be non-negative")


class NegotiationEnvironment:
    """Runs a two-party negotiation while preserving private tool traces.

    The environment is steppable: ``step()`` advances exactly one agent
    action, which lets a market-level scheduler interleave many concurrent
    negotiations. ``run()`` simply steps to completion.
    """

    def __init__(
        self,
        scenario: Scenario,
        buyer: AgentPort,
        seller: AgentPort,
        tools: tuple[ToolPort, ...] = (),
        tool_configs: tuple[ToolRuntimeConfig, ...] | None = None,
        transaction_simulator: TransactionPort | None = None,
        rules: NegotiationRules | None = None,
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
        self.rules = rules
        self.events: list[TranscriptEvent] = []
        self._latest_offer_role: Role | None = None
        self._latest_offer_price: float | None = None
        self._latest_offer_public_turn: int | None = None
        self._offer_counts: dict[Role, int] = {Role.BUYER: 0, Role.SELLER: 0}
        self._actor: AgentPort = self.buyer
        self._public_turns = 0
        self._total_steps = 0
        self._final_result: RunResult | None = None

    @property
    def result(self) -> RunResult | None:
        return self._final_result

    @property
    def is_complete(self) -> bool:
        return self._final_result is not None

    def run(self) -> RunResult:
        while self._final_result is None:
            self.step()
        return self._final_result

    def step(self) -> TranscriptEvent | None:
        """Advance the negotiation by exactly one agent action.

        Returns the recorded event, or None once the run has finished
        (including the call that finalizes a timeout).
        """

        if self._final_result is not None:
            return None
        max_total_steps = self.scenario.max_turns * 4
        if (
            self._public_turns >= self.scenario.max_turns
            or self._total_steps >= max_total_steps
        ):
            self._final_result = self._build_result("timeout", None)
            return None

        self._expire_standing_offer_if_due()
        self._total_steps += 1
        actor = self._actor
        context = self._context_for(actor.role)
        action = actor.act(context)
        event = self._event_from_action(self._total_steps, actor, action, context)
        self.events.append(event)

        if action.type == ActionType.TOOL_CALL:
            return event

        self._public_turns += 1
        if action.type == ActionType.OFFER and action.offer is not None:
            if self._offer_exceeds_cap(actor.role):
                self._final_result = self._build_result("invalid_offer", None)
                return event
            self._offer_counts[actor.role] += 1
            self._latest_offer_role = actor.role
            self._latest_offer_price = action.offer.price
            self._latest_offer_public_turn = self._public_turns
            self._actor = self._next_actor(actor)
            return event

        if action.type == ActionType.ACCEPT:
            outcome, deal_price = self._accept_outcome(actor.role)
            transaction = self._settle_transaction(
                accepting_role=actor.role,
                deal_price=deal_price,
                next_turn=self._total_steps + 1,
            )
            self._final_result = self._build_result(outcome, deal_price, transaction)
            return event

        if action.type == ActionType.REJECT:
            self._final_result = self._build_result("rejected", None)
            return event

        if action.type == ActionType.GHOST:
            self._final_result = self._build_result("ghosted", None)
            return event

        self._actor = self._next_actor(actor)
        return event

    def _expire_standing_offer_if_due(self) -> None:
        if (
            self.rules is None
            or self.rules.offer_expiry_turns is None
            or self._latest_offer_role is None
            or self._latest_offer_public_turn is None
        ):
            return
        age = self._public_turns - self._latest_offer_public_turn
        if age >= self.rules.offer_expiry_turns:
            self._append_rule_event(
                f"offer_expired:{self._latest_offer_role.value}"
            )
            self._latest_offer_role = None
            self._latest_offer_price = None
            self._latest_offer_public_turn = None

    def _offer_exceeds_cap(self, role: Role) -> bool:
        if self.rules is None or self.rules.max_offers_per_side is None:
            return False
        if self._offer_counts[role] < self.rules.max_offers_per_side:
            return False
        self._append_rule_event(f"offer_cap_exceeded:{role.value}")
        return True

    def _append_rule_event(self, content: str) -> None:
        self._total_steps += 1
        self.events.append(
            TranscriptEvent(
                turn=self._total_steps,
                role=Role.SYSTEM,
                actor=RULES_ACTOR,
                action_type=ActionType.MESSAGE,
                content=content,
                private=False,
            )
        )

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
            if self.scenario.seller_true_condition is not None:
                # The seller alone knows the item's true condition; the buyer
                # sees only the public claim on the product.
                private_state["true_condition"] = self.scenario.seller_true_condition
            if self.scenario.seller_true_quality is not None:
                # Numeric truth on the same [0, 1] axis the inspect tool reports.
                private_state["true_quality"] = self.scenario.seller_true_quality
        outside_option = self._own_side_batna(role)
        if outside_option is not None:
            private_state["outside_option"] = outside_option
        rule_state = self._rule_state(role)
        if rule_state is not None:
            private_state["negotiation_rules"] = rule_state
        return AgentContext(
            scenario=self.scenario,
            role=role,
            transcript=visible_events,
            available_tools=self._available_tools_for(role),
            private_state=private_state,
        )

    def _own_side_batna(self, role: Role) -> Mapping[str, object] | None:
        """Surface this side's outside-option derivation, never the counterpart's."""

        batna = self.scenario.metadata.get("batna")
        if not isinstance(batna, Mapping):
            return None
        side = batna.get("buyer" if role == Role.BUYER else "seller")
        if not isinstance(side, Mapping):
            return None
        return dict(side)

    def _rule_state(self, role: Role) -> Mapping[str, object] | None:
        if self.rules is None:
            return None
        state: dict[str, object] = {
            "turn_delay_cost": self.rules.turn_delay_cost,
        }
        if self.rules.max_offers_per_side is not None:
            state["remaining_offers"] = max(
                0, self.rules.max_offers_per_side - self._offer_counts[role]
            )
        if self.rules.offer_expiry_turns is not None:
            state["offer_expiry_turns"] = self.rules.offer_expiry_turns
            if self._latest_offer_public_turn is not None:
                state["standing_offer_age_turns"] = (
                    self._public_turns - self._latest_offer_public_turn
                )
        return state

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

    def _build_result(
        self,
        outcome: str,
        deal_price: float | None,
        transaction: TransactionOutcome | None = None,
    ) -> RunResult:
        metrics = dict(
            compute_metrics(self.scenario, outcome, deal_price, self.events)
        )
        if self.rules is not None and self.rules.turn_delay_cost > 0:
            metrics["turn_delay_cost_total"] = (
                self.rules.turn_delay_cost * self._public_turns
            )
        return RunResult(
            scenario=self.scenario,
            events=tuple(self.events),
            outcome=outcome,
            deal_price=deal_price,
            completed_turns=self._public_turns,
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
