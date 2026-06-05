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

## Config Runner Registration

Python API users can run custom `AgentPort` implementations through the same
config runner used by no-key benchmark runs:

```python
from opennego.runner import run_experiment_config
from opennego.schema import Role


def my_buyer_factory(role, params):
    if role != Role.BUYER:
        raise ValueError("my_buyer requires buyer role")
    return MyBuyerAgent(
        name=params.get("name", "my_buyer"),
        max_price=float(params["max_price"]),
    )


summary = run_experiment_config(
    "configs/my_eval.yaml",
    agent_factories={"my_buyer": my_buyer_factory},
)
```

The config references the registered factory key and passes optional params:

```json
{
  "agents": {
    "buyer": {
      "kind": "my_buyer",
      "params": {"name": "team_a_buyer", "max_price": 760}
    },
    "seller": {"kind": "scripted_seller"}
  }
}
```

Factories receive `(role, params)` and must return a fresh agent with matching
`role`, a non-empty `name`, and callable `act(context)`. The runner validates
unknown kinds and wrong-role agents before creating run outputs. The generated
manifest records the configured `kind` and runtime agent `name`.

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

## Current Runner Boundary

The CLI intentionally does not import arbitrary Python modules. Use the Python
API registration path above for custom local agents. Provider-backed LLM agents
should still stay behind `LLMPort` and adapter modules rather than importing
provider SDKs into the environment layer.

## Sparring Against NPC Profiles

Custom user agents can also spar against curated marketplace NPC profiles
through the Python API:

```python
from opennego.sparring import run_sparring_suite


def user_agent_factory(role):
    return MyBuyerAgent(name="team_a_buyer")


summary = run_sparring_suite(
    output_dir="/tmp/team-a-sparring",
    user_role="buyer",
    opponent_profile_ids=("seller_hardline_anchor_v1",),
    user_agent_factory=user_agent_factory,
    user_agent_kind="team_a_buyer",
)
```

The suite instantiates a fresh user agent for each profile-backed run and
validates that the returned role matches `user_role`. Generated manifests record
the custom `user_agent_kind` and runtime agent name. This path cannot be
combined with `user_strategy_path`; use either a concrete custom agent or a
versioned strategy-candidate user agent in one run.
