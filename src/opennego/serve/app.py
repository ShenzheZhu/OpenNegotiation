"""Stdlib HTTP transport for the local web client.

Thin routing over ``ServeService``; no business logic. Static assets (added
in #167) are served from ``opennego/serve/static/``.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping

from opennego.serve.service import ServeError, ServeService

STATIC_DIR = Path(__file__).parent / "static"
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

# (method, compiled path) -> handler(service, match, body) -> (status, payload)
Route = Callable[[ServeService, "re.Match[str]", Mapping[str, Any]], Any]
_ROUTES: list[tuple[str, "re.Pattern[str]", Route]] = []


def _route(method: str, pattern: str) -> Callable[[Route], Route]:
    compiled = re.compile(f"^{pattern}$")

    def register(func: Route) -> Route:
        _ROUTES.append((method, compiled, func))
        return func

    return register


@_route("GET", r"/api/health")
def _health(service, match, body):
    return {"status": "ok"}


@_route("GET", r"/api/profiles")
def _profiles(service, match, body):
    return service.profiles()


@_route("GET", r"/api/agents")
def _list_agents(service, match, body):
    return {"agents": list(service.list_agents())}


@_route("POST", r"/api/agents")
def _define_agent(service, match, body):
    return service.define_agent(body)


@_route("GET", r"/api/agents/(?P<agent_id>[^/]+)")
def _get_agent(service, match, body):
    return service.get_agent(match.group("agent_id"))


@_route("POST", r"/api/agents/(?P<agent_id>[^/]+)/strategy")
def _decide_strategy(service, match, body):
    return service.decide_strategy(match.group("agent_id"), body)


@_route("POST", r"/api/matches")
def _run_match(service, match, body):
    return service.run_match(body)


@_route("GET", r"/api/runs/(?P<run_id>[^/]+)/trace")
def _trace(service, match, body):
    return service.get_trace(match.group("run_id"))


@_route("GET", r"/api/runs/(?P<run_id>[^/]+)/report")
def _report(service, match, body):
    return service.get_report(match.group("run_id"))


@_route("POST", r"/api/runs/(?P<run_id>[^/]+)/evolve")
def _evolve(service, match, body):
    parent = str(body.get("parent_strategy_id", "user_strategy_v0"))
    return service.evolve(match.group("run_id"), parent_strategy_id=parent)


@_route("GET", r"/api/ratings")
def _ratings(service, match, body):
    return service.ratings()


def dispatch(
    service: ServeService,
    method: str,
    path: str,
    body: Mapping[str, Any] | None = None,
) -> tuple[int, Any]:
    """Route one request to a handler. Returns (status, payload).

    Pure function over the service — the unit-test entry point, no socket.
    """

    for route_method, pattern, handler in _ROUTES:
        if route_method != method:
            continue
        match = pattern.match(path)
        if match is None:
            continue
        try:
            return 200, handler(service, match, body or {})
        except ServeError as exc:
            return 400, {"error": str(exc)}
        except (OSError, ValueError, KeyError) as exc:
            return 500, {"error": str(exc)}
    return 404, {"error": f"no route for {method} {path}"}


def make_handler(service: ServeService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # quiet by default
            pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/"):
                self._api("GET")
            else:
                self._static()

        def do_POST(self) -> None:  # noqa: N802
            self._api("POST")

        def _api(self, method: str) -> None:
            body: Mapping[str, Any] = {}
            if method == "POST":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b""
                if raw:
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError:
                        self._send_json(400, {"error": "invalid JSON body"})
                        return
            status, payload = dispatch(service, method, self.path, body)
            self._send_json(status, payload)

        def _static(self) -> None:
            rel = self.path.lstrip("/") or "index.html"
            target = (STATIC_DIR / rel).resolve()
            if STATIC_DIR not in target.parents or not target.is_file():
                self._send_json(404, {"error": "not found"})
                return
            content = target.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                _CONTENT_TYPES.get(target.suffix, "application/octet-stream"),
            )
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, status: int, payload: Any) -> None:
            from opennego.artifacts import to_jsonable

            data = json.dumps(to_jsonable(payload)).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: str | Path = "runs/serve",
    config_path: str = "configs/real_market_demo.yaml",
) -> None:
    service = ServeService.create(data_dir, config_path=config_path)
    server = ThreadingHTTPServer((host, port), make_handler(service))
    scheme = "http"
    print(f"opennego serve on {scheme}://{host}:{port} (data-dir={data_dir})")
    if host not in ("127.0.0.1", "localhost"):
        print(
            "WARNING: binding off localhost. BYOK keys are sent to this server; "
            "do not expose it on an untrusted network."
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
