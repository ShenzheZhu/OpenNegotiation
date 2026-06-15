"""Local web client for OpenNegotiation (`opennego serve`).

A stdlib-only HTTP backend (see ``docs/design/serve.md``) that wraps the
existing Python API. ``service.ServeService`` holds the delegating logic and
is tested directly; ``app`` is the thin ``http.server`` transport.
"""

from .service import ServeError, ServeService

__all__ = ["ServeError", "ServeService"]
