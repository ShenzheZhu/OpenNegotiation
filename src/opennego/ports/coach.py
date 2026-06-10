"""Provider-neutral coach contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from opennego.coaching import BattleReport, CoachCase


@runtime_checkable
class CoachPort(Protocol):
    """Reviews one completed run from the user's perspective.

    Implementations receive a filtered :class:`CoachCase` — exactly what the
    user agent could have seen plus the opponent's public card — and return a
    structured ``opennego.battle_report.v2`` report. They must never receive
    or infer access to counterpart private state; the case builder enforces
    that boundary.
    """

    kind: str

    def review(self, case: "CoachCase") -> "BattleReport":
        ...
