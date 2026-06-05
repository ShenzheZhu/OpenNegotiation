# Agent Integration Guide

This guide is for external teams plugging a negotiation model into OpenNego.

## Option 1: Implement `AgentPort`

Implement:

```python
from opennego.ports import AgentPort
from opennego.schema import AgentAction, AgentContext, Role


class MyBuyerAgent(AgentPort):
    name = "my_buyer"
    role = Role.BUYER

    def act(self, context: AgentContext) -> AgentAction:
        ...
```

`AgentContext` provides:

- `scenario`: product, budget/reservation constraints, max turns
- `role`: current role
- `transcript`: visible prior events
- `available_tools`: tool names available under the active regime
- `private_state`: budget for buyer or reservation price for seller

Return one `AgentAction`:

- `AgentAction.tool(name, arguments)`
- `AgentAction.offer_price(price, note)`
- `AgentAction.accept(note)`
- `AgentAction.reject(note)`
- `AgentAction.message(content)`

Private tool events are only visible to the caller during the run, but all tool
events are written to artifacts for audit.

## Option 2: Use `LLMNegotiationAgent`

Use the built-in LLM baseline when your model can emit the OpenNego structured
action JSON:

```python
from opennego.adapters import LiteLLMGateway
from opennego.agents import make_llm_buyer

gateway = LiteLLMGateway(model_aliases={"buyer": "openai/gpt-4o-mini"})
buyer = make_llm_buyer(
    llm=gateway,
    model="buyer",
    tool_policy="available",
)
```

Install optional dependencies only for live provider runs:

```bash
python -m pip install -e ".[llm]"
```

Keep API keys in environment variables or a LiteLLM proxy configuration. Never
commit keys, cookies, or live marketplace traces.

## Structured LLM Action JSON

The LLM baseline expects one JSON object:

```json
{"type": "offer", "price": 750, "note": "My offer is $750."}
```

Tool-aware agents can return:

```json
{
  "type": "tool_call",
  "tool": {
    "name": "market_price_search",
    "arguments": {
      "query": "Sony Alpha a6400 Mirrorless Camera Body",
      "condition": "used",
      "limit": 5
    }
  }
}
```

No-tool agents cannot call tools even when the environment has them. The parser
rejects disallowed tool calls and triggers the repair prompt.

## Current Runner Integration

The config runner currently instantiates built-in scripted baselines. External
teams can integrate custom agents by importing the Python API and constructing a
`NegotiationEnvironment` directly. Runner-level custom agent registration is a
planned extension after the first benchmark handoff.
