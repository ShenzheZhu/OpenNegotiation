"""Agent port for negotiation policies."""

from __future__ import annotations

from typing import Protocol

from opennego.schema import AgentAction, AgentContext, Role


class AgentPort(Protocol):
    """Provider-neutral interface for buyer and seller agents."""

    name: str
    role: Role

    def act(self, context: AgentContext) -> AgentAction:
        ...
