import builtins
import sys
import types

import pytest

from opennego.adapters import LiteLLMGateway
from opennego.ports import LLMRequest


def test_litellm_gateway_maps_request_and_response(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return {
            "model": "openai/gpt-test",
            "choices": [
                {
                    "message": {"content": "offer $750", "tool_calls": []},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
                "cost": 0.001,
            },
        }

    fake_litellm = types.SimpleNamespace(completion=fake_completion)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    gateway = LiteLLMGateway(model_aliases={"buyer-default": "openai/gpt-test"})
    response = gateway.complete(
        LLMRequest(
            model="buyer-default",
            messages=[{"role": "user", "content": "negotiate"}],
            temperature=0.2,
            max_tokens=64,
            metadata={"run_id": "fixture"},
        )
    )

    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "negotiate"}],
            "temperature": 0.2,
            "max_tokens": 64,
            "metadata": {"run_id": "fixture"},
        }
    ]
    assert response.model == "openai/gpt-test"
    assert response.content == "offer $750"
    assert response.finish_reason == "stop"
    assert response.usage.total_tokens == 14
    assert response.usage.cost_usd == 0.001


def test_litellm_gateway_preserves_zero_cost(monkeypatch):
    def fake_completion(**kwargs):
        return {
            "model": kwargs["model"],
            "choices": [{"message": {"content": ""}}],
            "usage": {"cost": 0.0},
        }

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(completion=fake_completion))

    response = LiteLLMGateway().complete(LLMRequest(model="openai/free-model", messages=[]))

    assert response.usage.cost_usd == 0.0


def test_litellm_gateway_has_clear_missing_dependency_error(monkeypatch):
    monkeypatch.delitem(sys.modules, "litellm", raising=False)
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "litellm":
            raise ImportError("blocked in test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    gateway = LiteLLMGateway()

    with pytest.raises(RuntimeError, match="LiteLLM is not installed"):
        gateway.complete(LLMRequest(model="openai/gpt-test", messages=[]))
