# Local Web Client: `opennego serve`

Status: proposed (issue #165). Review before building the backend (#166) or
the UI (#167–#169).

## Goals

- A local, single-user web client for the core loop: define your agent →
  run a match → read the coach's battle report → accept/reject an evolved
  strategy → see your ratings.
- Hold the project's two hard lines at the UI layer: zero new runtime
  dependencies, and BYOK keys that never leave the user's machine.
- The server is a thin transport over the existing Python API — no new
  negotiation, coaching, evolution, or rating logic lives in it.

## Non-Goals

- Multi-tenant hosting, accounts, or auth (noted for a future hosted arena,
  not built here).
- Market-mode UI (M5).
- A frontend build toolchain (no npm, bundler, or framework).

## Stack Decision: stdlib `http.server`

**Decision: stdlib `http.server` + `ThreadingHTTPServer`, vanilla
no-build frontend. No FastAPI/uvicorn, no new runtime dependency.**

Rationale:

- The project ships zero runtime dependencies (only an optional `[llm]`
  extra). A local single-user UI does not justify a web framework + ASGI
  server in the default install. `http.server` is sufficient for localhost
  JSON endpoints and serving a handful of static assets.
- Keeping it dependency-free means `pip install opennego` gives you the full
  client with no extras, matching the rest of the tool.
- If a hosted multi-tenant arena is built later, that is a separate deployable
  with its own (optional) framework dependency; it does not change the local
  client.

Trade-off accepted: we hand-roll routing and JSON handling (small, tested)
rather than get it from a framework. The handler stays thin because all work
delegates to existing modules.

## Architecture

```text
browser (static HTML/CSS/JS, fetch)
   |  JSON over localhost
opennego serve  (stdlib ThreadingHTTPServer)
   -> request handler: route + parse + delegate
   -> opennego.sparring / coaching / evolution / strategy_config /
      strategy_lineage / rating / leaderboard
   -> data-dir: agents/, runs/, ratings.db, lineage/
```

- `opennego serve [--host 127.0.0.1] [--port 8765] [--data-dir runs/serve]`.
- Binds to `127.0.0.1` by default. A non-localhost bind prints an explicit
  warning (keys would traverse the network).
- Static assets are packaged under `opennego/serve/static/` and served by the
  same handler.

## HTTP API

All requests/responses are JSON (`Content-Type: application/json`); errors are
`{"error": "..."}` with a 4xx/5xx status. Every endpoint maps to an existing
Python entry point.

| Method | Path | Body | Delegates to | Returns |
| --- | --- | --- | --- | --- |
| GET | `/api/health` | — | — | `{status, version}` |
| GET | `/api/profiles` | — | `learning.registry_listing` | NPC profile cards (public fields) |
| POST | `/api/agents` | `{id, role, model?, endpoint?, key?, strategy_prompt}` | `strategy_config` layer | agent summary (no key) |
| GET | `/api/agents` | — | data-dir read | agent summaries (no keys) |
| POST | `/api/matches` | `{agent_id, opponent_profile_id}` | `sparring.run_sparring_suite` | run id + trace summary |
| GET | `/api/runs/{run_id}/trace` | — | artifact read | ordered visible trace events |
| GET | `/api/runs/{run_id}/report` | — | `coaching.review_run` (rules coach) | battle report v2 |
| POST | `/api/runs/{run_id}/evolve` | — | `evolution.generate_strategy_candidate` | candidate + diff + generalization verdict |
| POST | `/api/agents/{id}/strategy` | `{candidate_id, decision}` | `strategy_config` + `strategy_lineage` | new strategy version + lineage node |
| GET | `/api/ratings` | — | `leaderboard.build_rating_leaderboard` | `opennego.leaderboard.v2` |

The LLM coach is opt-in per request later; the default report endpoint uses
the deterministic rule coach so the UI works with no key.

## Security Model

- **Keys are write-only at the boundary.** A `key` may be POSTed when defining
  an agent. It is held only as needed to construct the live agent for a run
  and is **never** written to disk in plaintext and **never** returned by any
  GET. Agent summaries omit the key field entirely. (Persisting an agent saves
  model/endpoint/strategy prompt only; the user re-enters the key per session,
  or sets it via the same environment variables the CLI uses.)
- **Localhost by default.** No auth for the single-user local case. A startup
  banner states the bind address and that keys are local-only.
- **What hosted multi-tenant would add (not built):** per-user auth, a secret
  manager for keys, TLS, and rate limiting. Called out so the local design
  does not accidentally foreclose it — the API shapes are tenant-agnostic.

## Frontend

- Static `index.html` + one CSS + a small JS module per view (agent, match,
  report, ratings), no framework, no build step.
- The agent view shows the editable strategy prompt next to a **read-only**
  base prompt panel (the fixed sandbox protocol), making the two-layer
  contract visible.
- Views call the JSON API with `fetch`; the server also serves the static
  files so there is no CORS or separate dev server.

## Test Plan

- Backend: drive the request handler directly (no socket) for each endpoint
  with deterministic agents; assert key never appears in any response or
  on-disk agent file.
- Frontend: smoke test that `index.html` and JS assets are served and
  well-formed; no browser automation required for M4.

## Out of Scope

- Backend implementation (#166), UI views (#167–#169), market mode (M5).
