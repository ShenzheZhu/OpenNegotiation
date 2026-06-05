"""LLM-backed baseline agents using the provider-neutral LLM port."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from opennego.artifacts import to_jsonable
from opennego.branding import PRODUCT_NAME
from opennego.learning import StrategyProfile
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
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["tool_call", "offer", "accept", "reject", "message"],
                },
                "content": {"type": ["string", "null"]},
                "price": {"type": ["number", "null"]},
                "note": {"type": ["string", "null"]},
                "tool": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "arguments": {
                            "type": ["object", "null"],
                            "additionalProperties": False,
                            "properties": {
                                "query": {"type": ["string", "null"]},
                                "condition": {"type": ["string", "null"]},
                                "limit": {"type": ["integer", "null"]},
                            },
                            "required": ["query", "condition", "limit"],
                        },
                    },
                    "required": ["name", "arguments"],
                },
            },
            "required": ["type", "content", "price", "note", "tool"],
        },
    },
}


class LLMActionParseError(ValueError):
    """Raised when an LLM response is not a valid OpenNegotiation action."""


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
    system_instructions: str | None = None

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
            {
                "role": "system",
                "content": _system_prompt(
                    self.role,
                    allowed_tools,
                    system_instructions=self.system_instructions,
                ),
            },
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


def make_profile_llm_agent(
    *,
    profile: StrategyProfile,
    llm: LLMPort,
    model: str,
    name: str | None = None,
    tool_policy: str = "available",
    temperature: float = 0.0,
    max_tokens: int | None = 512,
) -> LLMNegotiationAgent:
    """Create an LLM-backed NPC from a marketplace strategy profile."""

    return LLMNegotiationAgent(
        llm=llm,
        model=model,
        role=profile.role,
        name=name or f"llm_profile_{profile.role.value}:{profile.id}",
        tool_policy=tool_policy,
        temperature=temperature,
        max_tokens=max_tokens,
        system_instructions=_profile_system_instructions(profile),
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
    clean_arguments = {
        key: value for key, value in arguments.items() if value is not None
    }
    return AgentAction(
        type=ActionType.TOOL_CALL,
        content=_content(data),
        tool_call=ToolCall(name=tool_name, arguments=clean_arguments),
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


def _system_prompt(
    role: Role,
    allowed_tools: Sequence[str],
    *,
    system_instructions: str | None = None,
) -> str:
    tool_instruction = (
        "You may request exactly one available tool by returning a tool_call action."
        if allowed_tools
        else "You may not request tools. Do not return tool_call."
    )
    prompt = (
        f"You are a {PRODUCT_NAME} baseline negotiation agent. "
        f"Your role is {role.value}. "
        "Choose one next action for the current turn. "
        f"Return only valid JSON matching the {PRODUCT_NAME} action schema. "
        "Use type=offer with price for numeric offers, type=accept to accept the "
        "counterparty's latest offer, type=reject to end negotiation, type=message "
        "for non-binding text, and type=tool_call only when tools are allowed. "
        f"{tool_instruction}"
    )
    if system_instructions:
        prompt += f"\n\nMarketplace strategy profile:\n{system_instructions}"
    return prompt


def _profile_system_instructions(profile: StrategyProfile) -> str:
    traps = "\n".join(f"- {item}" for item in profile.expected_traps) or "- none"
    tools = ", ".join(profile.allowed_tools) or "none"
    return (
        f"Profile id: {profile.id}\n"
        f"Profile name: {profile.name}\n"
        f"Archetype: {profile.archetype}\n"
        f"Difficulty: {profile.difficulty}\n"
        f"Summary: {profile.summary}\n"
        f"Allowed tools declared by profile: {tools}\n"
        f"Base protocol prompt:\n{profile.base_prompt}\n"
        f"Strategy prompt:\n{profile.strategy_prompt}\n"
        f"Expected traps tested by this profile:\n{traps}"
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
        f"Your previous response was rejected by the {PRODUCT_NAME} action parser. "
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
    return str(data.get("content", "") or "")
