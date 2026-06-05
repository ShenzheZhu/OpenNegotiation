"""LLM port shared by provider adapters and LLM-backed agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: Sequence[Mapping[str, Any]]
    tools: Sequence[Mapping[str, Any]] | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    response_format: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    extra_params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    model: str
    content: str
    raw: Any = None
    tool_calls: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    finish_reason: str | None = None
    usage: LLMUsage = field(default_factory=LLMUsage)


class LLMPort(Protocol):
    """Unified model gateway interface used by OpenNego agents."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        ...
