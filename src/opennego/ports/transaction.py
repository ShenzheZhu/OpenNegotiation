"""Transaction settlement port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from opennego.schema import Scenario, TransactionOutcome


@dataclass(frozen=True)
class TransactionRequest:
    scenario: Scenario
    negotiated_price: float
    accepting_role: str


class TransactionPort(Protocol):
    """Provider-neutral interface for post-negotiation settlement."""

    def settle(self, request: TransactionRequest) -> TransactionOutcome:
        ...
