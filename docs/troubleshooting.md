# Troubleshooting

## No-Key Smoke Fails To Start

Run from the repository root:

```bash
opennego run --config configs/no_key_smoke.yaml
```

The config uses relative paths such as `examples/data/products.json`, so running
from another directory can make product or tool source files look missing.

## YAML Parse Error

The bundled smoke config is JSON-compatible YAML and does not require PyYAML.
If you use richer YAML syntax, install PyYAML locally or keep configs in JSON
syntax with a `.yaml` extension.

## LiteLLM Missing

Scripted tests do not require LiteLLM. Live LLM agents do:

```bash
python -m pip install -e ".[llm]"
```

Provider credentials must be supplied through environment variables or a LiteLLM
proxy. Do not add credentials to config files committed to git.

## LLM Action Parser Rejections

LLM baselines must return structured JSON, not prose. Common failures:

- missing `type`
- `offer` without `price`
- `tool_call` when `tool_policy="none"`
- tool name not present in `AgentContext.available_tools`
- malformed JSON

The baseline sends a repair prompt once by default. Repeated failures become a
non-binding message action so traces remain inspectable.

## Tool Failure Events

Tool errors should appear in `trace.jsonl` as events with:

```json
{"ok": false, "error": "..."}
```

They should not crash the environment unless the tool runtime config sets
`fail_fast: true`.

## Transaction Metrics Look Different From Deal Price

`deal_price` is the negotiated product price. Transaction metrics include
shipping, tax, escrow, payment fees, seller fees, and risk placeholders. For
example, a deal at `760.0` can have buyer total cost `858.0`.
