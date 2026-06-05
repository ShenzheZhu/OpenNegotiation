# LLM Baseline Agents

OpenNego LLM baselines live behind `LLMPort`. They do not import LiteLLM or any
provider SDK directly. Provider-specific behavior belongs in adapters such as
`LiteLLMGateway`.

## Agent Kinds

- `make_llm_buyer(...)`: creates a buyer-side LLM baseline.
- `make_llm_seller(...)`: creates a seller-side LLM baseline.
- `LLMNegotiationAgent`: generic role-configurable baseline.

Important fields:

- `llm`: provider-neutral `LLMPort` implementation.
- `model`: model alias passed to the gateway.
- `role`: `buyer` or `seller`.
- `temperature`: sampling temperature.
- `tool_policy`: `none` or `available`.

`tool_policy="none"` prevents tool calls even when the environment has tools.
`tool_policy="available"` permits only tools listed in the current
`AgentContext.available_tools`.

## Structured Action Contract

Agents must return one JSON object. Natural-language action scraping is
intentionally not supported.

Supported actions:

```json
{"type": "offer", "price": 750, "note": "My offer is $750."}
{"type": "accept", "note": "Accepted."}
{"type": "reject", "note": "No deal."}
{"type": "message", "content": "Can you include shipping?"}
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

If the model returns malformed JSON, an unsupported action, or a disallowed
tool call, the agent sends one repair prompt by default and asks for a corrected
JSON action. If repair still fails, the agent returns a non-binding `message`
action containing the parser failure.

## LiteLLM Usage

Install the optional LLM dependencies before using the LiteLLM adapter:

```bash
python -m pip install -e ".[llm]"
```

Keep provider credentials in environment variables or a LiteLLM proxy config.
Do not commit keys or live provider traces.

## Five-Model Demo

OpenNego includes a tiny live-model demo command:

```bash
opennego run-models --output-dir /tmp/opennego-five-model-demo
opennego report --input-dir /tmp/opennego-five-model-demo --output /tmp/opennego-five-model-demo.html
```

The default model set uses LiteLLM OpenRouter model IDs so one provider key can
cover multiple frontier and open-weight model families:

- `openrouter/openai/gpt-5.4-pro`
- `openrouter/anthropic/claude-opus-4.8`
- `openrouter/google/gemini-3.1-pro-preview`
- `openrouter/x-ai/grok-4.3`
- `openrouter/qwen/qwen3-235b-a22b`

This command runs each model as the buyer-side LLM agent against the scripted
seller on the real-market fixture. It writes the same benchmark artifacts as the
main runner, so `opennego report` can render the results as a leaderboard
preview.

This is intentionally a small demo path, not a batch benchmark. For cost and
latency control, prefer a low turn/token budget during live demos:

```bash
opennego run-models --output-dir /tmp/opennego-five-model-demo --max-turns 4 --max-tokens 256
```

The command writes `/tmp/opennego-five-model-demo/summary.json` for the full
attempt. Completed model directories contain the normal benchmark artifacts.
Failed model directories contain `failure.json` with redacted error text and
usage counters, so provider failures remain auditable without storing raw
provider payloads or credentials.
