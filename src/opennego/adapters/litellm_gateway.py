"""LiteLLM-backed implementation of the OpenNegotiation LLM port."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any, Mapping

from opennego.ports import LLMPort, LLMRequest, LLMResponse, LLMUsage


class LiteLLMGateway(LLMPort):
    """Call any LiteLLM-supported provider through the OpenNegotiation LLM port.

    The dependency is imported lazily so scripted agents and deterministic tests
    do not require LiteLLM or provider credentials.
    """

    def __init__(self, model_aliases: Mapping[str, str] | None = None) -> None:
        self.model_aliases = dict(model_aliases or {})

    def complete(self, request: LLMRequest) -> LLMResponse:
        litellm = self._load_litellm()
        model = self.model_aliases.get(request.model, request.model)
        params: dict[str, Any] = {
            "model": model,
            "messages": list(request.messages),
            "temperature": request.temperature,
        }
        if request.tools is not None:
            params["tools"] = list(request.tools)
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.response_format is not None:
            params["response_format"] = dict(request.response_format)
        if request.metadata:
            params["metadata"] = dict(request.metadata)
        params.update(dict(request.extra_params))

        raw_response = litellm.completion(**params)
        return self._to_response(request_model=request.model, raw_response=raw_response)

    def _load_litellm(self) -> Any:
        try:
            import litellm  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "LiteLLM is not installed. Install OpenNegotiation with the optional "
                "LLM dependencies: python -m pip install -e '.[llm]'"
            ) from exc
        return litellm

    def _to_response(self, request_model: str, raw_response: Any) -> LLMResponse:
        choice = _get_first_choice(raw_response)
        message = _get(choice, "message", default={}) if choice is not None else {}
        content = _get(message, "content", default="") or ""
        tool_calls = _get(message, "tool_calls", default=()) or ()
        usage = _usage_from_raw(raw_response)
        model = str(_get(raw_response, "model", default=request_model) or request_model)
        finish_reason = _get(choice, "finish_reason", default=None) if choice is not None else None
        return LLMResponse(
            model=model,
            content=str(content),
            raw=raw_response,
            tool_calls=tuple(_normalize_tool_call(call) for call in tool_calls),
            finish_reason=str(finish_reason) if finish_reason is not None else None,
            usage=usage,
        )


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, MappingABC):
        return value.get(key, default)
    return getattr(value, key, default)


def _get_first_choice(raw_response: Any) -> Any:
    choices = _get(raw_response, "choices", default=())
    if not choices:
        return None
    return choices[0]


def _usage_from_raw(raw_response: Any) -> LLMUsage:
    usage = _get(raw_response, "usage", default={}) or {}
    cost = _as_float(_get(usage, "cost"))
    if cost is None:
        cost = _as_float(_get(usage, "cost_usd"))
    return LLMUsage(
        prompt_tokens=_as_int(_get(usage, "prompt_tokens")),
        completion_tokens=_as_int(_get(usage, "completion_tokens")),
        total_tokens=_as_int(_get(usage, "total_tokens")),
        cost_usd=cost,
    )


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_tool_call(tool_call: Any) -> Mapping[str, Any]:
    if isinstance(tool_call, MappingABC):
        return dict(tool_call)
    if hasattr(tool_call, "model_dump"):
        return dict(tool_call.model_dump())
    if hasattr(tool_call, "dict"):
        return dict(tool_call.dict())
    return {
        key: getattr(tool_call, key)
        for key in ("id", "type", "function")
        if hasattr(tool_call, key)
    }
