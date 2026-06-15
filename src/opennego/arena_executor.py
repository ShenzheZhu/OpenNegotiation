"""Execute a reciprocal arena plan into rated matches.

``arena.py`` only schedules matchups. This module runs each matchup through
the deterministic ``NegotiationEnvironment``, scores both sides with the
normalized-surplus rating (``opennego.rating``), and ingests the result into a
``RatingStore``. Ingestion is keyed by matchup id, so reruns are idempotent;
self-play rows are recorded but never move ratings (handled by the store).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.arena import ArenaPlan, load_arena_plan
from opennego.artifacts import write_json
from opennego.environment import NegotiationEnvironment
from opennego.ports import AgentPort
from opennego.rating import RatingStore, compute_match_score
from opennego.schema import ActionType, Role, Scenario

ARENA_RUN_SCHEMA_VERSION = "opennego.arena_run.v1"

# (participant_id, role) -> agent. The default treats every participant as the
# generic deterministic baseline for its role; callers pass a real factory to
# pit distinct strategies against each other.
ArenaAgentFactory = Callable[[str, Role], AgentPort]


def default_arena_agent_factory(participant_id: str, role: Role) -> AgentPort:
    if role == Role.BUYER:
        return ToolAwareBuyer(name=participant_id)
    return ScriptedSeller(name=participant_id)


@dataclass(frozen=True)
class ArenaRunSummary:
    schema_version: str
    status: str
    plan_path: str | None
    store_path: str
    output_dir: str | None
    matchups_total: int
    matchups_executed: int
    matchups_skipped_existing: int
    rated_matchups: int
    self_play_matchups: int


def run_arena(
    *,
    plan: ArenaPlan,
    scenario: Scenario,
    store: RatingStore,
    agent_factory: ArenaAgentFactory | None = None,
    output_dir: str | Path | None = None,
    plan_path: str | Path | None = None,
) -> ArenaRunSummary:
    """Run every matchup in a plan and ingest scored results into the store."""

    factory = agent_factory or default_arena_agent_factory
    output = Path(output_dir) if output_dir is not None else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)

    executed = 0
    skipped = 0
    rated = 0
    self_play = 0
    for matchup in plan.matchups:
        buyer = factory(matchup.buyer_participant_id, Role.BUYER)
        seller = factory(matchup.seller_participant_id, Role.SELLER)
        env = NegotiationEnvironment(scenario=scenario, buyer=buyer, seller=seller)
        result = env.run()
        ghost_walker = _ghost_walker(result)
        score = compute_match_score(
            outcome=result.outcome,
            deal_price=result.deal_price,
            buyer_budget=scenario.buyer_budget,
            seller_reservation=scenario.seller_reservation_price,
            market_reference=_market_reference(scenario),
            ghost_walker=ghost_walker,
        )
        is_self_play = (
            matchup.buyer_participant_id == matchup.seller_participant_id
        )
        ingested = store.ingest_match(
            run_id=matchup.matchup_id,
            scenario_id=matchup.scenario_id,
            buyer_participant_id=matchup.buyer_participant_id,
            seller_participant_id=matchup.seller_participant_id,
            outcome=result.outcome,
            deal_price=result.deal_price,
            score=score,
        )
        if not ingested:
            skipped += 1
            continue
        executed += 1
        if is_self_play:
            self_play += 1
        else:
            rated += 1
        if output is not None:
            write_json(
                output / f"{matchup.matchup_id}.json",
                {
                    "schema_version": ARENA_RUN_SCHEMA_VERSION,
                    "matchup_id": matchup.matchup_id,
                    "scenario_id": matchup.scenario_id,
                    "buyer_participant_id": matchup.buyer_participant_id,
                    "seller_participant_id": matchup.seller_participant_id,
                    "outcome": result.outcome,
                    "deal_price": result.deal_price,
                    "buyer_score": score.buyer,
                    "seller_score": score.seller,
                    "self_play": is_self_play,
                },
            )

    return ArenaRunSummary(
        schema_version=ARENA_RUN_SCHEMA_VERSION,
        status="completed",
        plan_path=str(plan_path) if plan_path is not None else None,
        store_path=store.path,
        output_dir=str(output) if output is not None else None,
        matchups_total=len(plan.matchups),
        matchups_executed=executed,
        matchups_skipped_existing=skipped,
        rated_matchups=rated,
        self_play_matchups=self_play,
    )


def run_arena_from_paths(
    *,
    plan_path: str | Path,
    scenario: Scenario,
    store_path: str | Path,
    agent_factory: ArenaAgentFactory | None = None,
    output_dir: str | Path | None = None,
) -> ArenaRunSummary:
    """Convenience wrapper: load a plan and store from paths, then run."""

    plan = load_arena_plan(plan_path)
    store = RatingStore(store_path)
    try:
        return run_arena(
            plan=plan,
            scenario=scenario,
            store=store,
            agent_factory=agent_factory,
            output_dir=output_dir,
            plan_path=plan_path,
        )
    finally:
        store.close()


def _market_reference(scenario: Scenario) -> float | None:
    reference = scenario.product.market_reference
    return reference.reference_price if reference is not None else None


def _ghost_walker(result) -> Role | None:
    for event in reversed(result.events):
        if event.action_type == ActionType.GHOST:
            return event.role
    return None
