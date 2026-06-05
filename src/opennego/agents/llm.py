"""LLM-backed baseline agents using the provider-neutral LLM port."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from opennego.artifacts import to_jsonable
from opennego.ports import LLMPort, LLMRequest
from opennego.schema import (
    ActionType,
    AgentAction,
    AgentContext,
    Offer,
    Role,
    ToolCall,
    parse_price,
)

LLM_ACTION_RESPONSE_FORMAT: Mapping[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "opennego_agent_action",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["tool_call", "offer", "accept", "reject", "message"],
                },
                "content": {"type": "string"},
                "price": {"type": "number"},
                "note": {"type": "string"},
                "tool": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["name"],
                },
            },
            "required": ["type"],
        },
    },
}


class LLMActionParseError(ValueError):
    """Raised when an LLM response is not a valid OpenNego action."""


@dataclass
class LLMNegotiationAgent:
    """Baseline negotiation policy backed by an LLMPort."""

    llm: LLMPort
    model: str
    role: Role
    name: str
    tool_policy: str = "none"
    temperature: float = 0.0
    max_tokens: int | None = 512
    max_repair_attempts: int = 1

    def __post_init__(self) -> None:
        self.role = Role(self.role)
        if self.tool_policy not in {"none", "available"}:
            raise ValueError("tool_policy must be 'none' or 'available'")

    def act(self, context: AgentContext) -> AgentAction:
        allowed_tools = self._allowed_tools(context)
        messages = self._messages(context, allowed_tools)
        last_error: LLMActionParseError | None = None

        for attempt in range(self.max_repair_attempts + 1):
            response = self.llm.complete(
                LLMRequest(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    response_format=LLM_ACTION_RESPONSE_FORMAT,
                    metadata={
                        "agent_name": self.name,
                        "agent_role": self.role.value,
                        "repair_attempt": attempt,
                    },
                )
            )
            try:
                return parse_llm_agent_action(response.content, allowed_tools)
            except LLMActionParseError as exc:
                last_error = exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": _repair_prompt(exc, allowed_tools),
                    },
                ]

        return AgentAction.message(
            f"Invalid structured LLM action after repair: {last_error}"
        )

    def _allowed_tools(self, context: AgentContext) -> tuple[str, ...]:
        if self.tool_policy == "none":
            return ()
        return tuple(context.available_tools)

    def _messages(
        self,
        context: AgentContext,
        allowed_tools: Sequence[str],
    ) -> list[Mapping[str, Any]]:
        return [
            {"role": "system", "content": _system_prompt(self.role, allowed_tools)},
            {
                "role": "user",
                "content": json.dumps(
                    _context_payload(context, allowed_tools),
                    indent=2,
                    sort_keys=True,
                ),
            },
        ]


def make_llm_buyer(
    *,
    llm: LLMPort,
    model: str,
    name: str = "llm_buyer",
    tool_policy: str = "none",
    temperature: float = 0.0,
    max_tokens: int | None = 512,
) -> LLMNegotiationAgent:
    return LLMNegotiationAgent(
        llm=llm,
        model=model,
        role=Role.BUYER,
        name=name,
        tool_policy=tool_policy,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def make_llm_seller(
    *,
    llm: LLMPort,
    model: str,
    name: str = "llm_seller",
    tool_policy: str = "none",
    temperature: float = 0.0,
    max_tokens: int | None = 512,
) -> LLMNegotiationAgent:
    return LLMNegotiationAgent(
        llm=llm,
        model=model,
        role=Role.SELLER,
        name=name,
        tool_policy=tool_policy,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def parse_llm_agent_action(
    content: str,
    allowed_tools: Sequence[str] = (),
) -> AgentAction:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMActionParseError("response must be a JSON object") from exc
    if not isinstance(data, Mapping):
        raise LLMActionParseError("response must be a JSON object")

    action_type = _required_str(data, "type")
    if action_type == ActionType.TOOL_CALL.value:
        return _parse_tool_action(data, allowed_tools)
    if action_type == ActionType.OFFER.value:
        return _parse_offer_action(data)
    if action_type == ActionType.ACCEPT.value:
        return AgentAction.accept(_note(data))
    if action_type == ActionType.REJECT.value:
        return AgentAction.reject(_note(data))
    if action_type == ActionType.MESSAGE.value:
        return AgentAction.message(_content(data))
    raise LLMActionParseError(f"unsupported action type: {action_type!r}")


def _parse_tool_action(
    data: Mapping[str, Any],
    allowed_tools: Sequence[str],
) -> AgentAction:
    if not allowed_tools:
        raise LLMActionParseError("tool_call is not allowed by this agent policy")
    tool = data.get("tool")
    if not isinstance(tool, Mapping):
        raise LLMActionParseError("tool_call action requires a tool object")
    tool_name = _required_str(tool, "name")
    if tool_name not in set(allowed_tools):
        raise LLMActionParseError(f"tool {tool_name!r} is not available")
    arguments = tool.get("arguments", {})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise LLMActionParseError("tool.arguments must be an object")
    return AgentAction(
        type=ActionType.TOOL_CALL,
        content=_content(data),
        tool_call=ToolCall(name=tool_name, arguments=dict(arguments)),
    )


def _parse_offer_action(data: Mapping[str, Any]) -> AgentAction:
    if "price" not in data:
        raise LLMActionParseError("offer action requires price")
    note = _note(data)
    try:
        price = parse_price(data["price"])
        offer = Offer(price=price, note=note)
    except (TypeError, ValueError) as exc:
        raise LLMActionParseError(f"offer.price: {exc}") from exc
    return AgentAction(
        type=ActionType.OFFER,
        content=note,
        offer=offer,
    )


def _system_prompt(role: Role, allowed_tools: Sequence[str]) -> str:
    tool_instruction = (
        "You may request exactly one available tool by returning a tool_call action."
        if allowed_tools
        else "You may not request tools. Do not return tool_call."
    )
    return (
        "You are an OpenNego baseline negotiation agent. "
        f"Your role is {role.value}. "
        "Choose one next action for the current turn. "
        "Return only valid JSON matching the OpenNego action schema. "
        "Use type=offer with price for numeric offers, type=accept to accept the "
        "counterparty's latest offer, type=reject to end negotiation, type=message "
        "for non-binding text, and type=tool_call only when tools are allowed. "
        f"{tool_instruction}"
    )


def _context_payload(
    context: AgentContext,
    allowed_tools: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "role": context.role.value,
        "product": to_jsonable(context.scenario.product),
        "private_state": to_jsonable(context.private_state),
        "available_tools": list(allowed_tools),
        "transcript": [to_jsonable(event) for event in context.transcript],
    }


def _repair_prompt(
    error: LLMActionParseError,
    allowed_tools: Sequence[str],
) -> str:
    return (
        "Your previous response was rejected by the OpenNego action parser. "
        f"Parser error: {error}. "
        "Return one corrected JSON object only. "
        f"Available tools: {list(allowed_tools)}."
    )


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise LLMActionParseError(f"{key}: expected non-empty string")
    return value


def _note(data: Mapping[str, Any]) -> str:
    value = data.get("note", data.get("content", ""))
    return str(value or "")


def _content(data: Mapping[str, Any]) -> str:
    return str(data.get("content", ""))
