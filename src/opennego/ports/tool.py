"""Tool port for information and transaction interfaces."""

from __future__ import annotations

from typing import Mapping, Protocol

from opennego.schema import AgentContext


class ToolPort(Protocol):
    """Provider-neutral interface for tools exposed to agents."""

    name: str
    description: str

    def call(self, arguments: Mapping[str, object], context: AgentContext | None) -> Mapping[str, object]:
        ...
