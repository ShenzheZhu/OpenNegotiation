import json

import pytest

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.arena import load_arena_plan, write_arena_plan
from opennego.arena_executor import (
    ARENA_RUN_SCHEMA_VERSION,
    default_arena_agent_factory,
    run_arena,
    run_arena_from_paths,
)
from opennego.cli import main
from opennego.rating import RatingStore
from opennego.scenario_generator import generate_scenarios, load_products
from opennego.schema import Role


def _scenario():
    products = load_products("examples/data/real_market_products.json")
    return generate_scenarios(products, seed=13)[0]


def _plan(tmp_path, participants=("alice", "bob", "carol")):
    return write_arena_plan(
        tmp_path / "plan.json",
        participants=participants,
        scenario_ids=("real_market_demo",),
        seeds=(13,),
    )


def test_default_factory_returns_role_agents():
    assert isinstance(default_arena_agent_factory("x", Role.BUYER), ToolAwareBuyer)
    assert isinstance(default_arena_agent_factory("x", Role.SELLER), ScriptedSeller)


def test_run_arena_populates_both_role_tracks(tmp_path):
    plan = _plan(tmp_path)
    store = RatingStore()

    summary = run_arena(plan=plan, scenario=_scenario(), store=store)

    assert summary.schema_version == ARENA_RUN_SCHEMA_VERSION
    assert summary.matchups_executed == summary.matchups_total
    assert summary.rated_matchups == summary.matchups_total
    assert store.match_count() == plan.matchup_count
    assert store.ratings_for_role(Role.BUYER)
    assert store.ratings_for_role(Role.SELLER)


def test_run_arena_is_idempotent(tmp_path):
    plan = _plan(tmp_path)
    store = RatingStore()

    run_arena(plan=plan, scenario=_scenario(), store=store)
    before = {
        snap.participant_id: snap.rating
        for snap in store.ratings_for_role(Role.BUYER)
    }
    second = run_arena(plan=plan, scenario=_scenario(), store=store)
    after = {
        snap.participant_id: snap.rating
        for snap in store.ratings_for_role(Role.BUYER)
    }

    assert second.matchups_executed == 0
    assert second.matchups_skipped_existing == second.matchups_total
    assert before == after


def test_self_play_rows_do_not_affect_ratings(tmp_path):
    plan = write_arena_plan(
        tmp_path / "plan.json",
        participants=("alice", "bob"),
        scenario_ids=("real_market_demo",),
        seeds=(13,),
        include_self_play=True,
    )
    store = RatingStore()

    summary = run_arena(plan=plan, scenario=_scenario(), store=store)

    assert summary.self_play_matchups >= 1
    # alice appears in self-play; her rated match_count must come only from
    # cross matchups, never from self-play rows.
    alice_buyer = store.rating("alice", Role.BUYER)
    assert alice_buyer.match_count < summary.matchups_total


def test_run_arena_writes_per_matchup_artifacts(tmp_path):
    plan = _plan(tmp_path, participants=("alice", "bob"))
    store = RatingStore()
    out = tmp_path / "matches"

    run_arena(plan=plan, scenario=_scenario(), store=store, output_dir=out)

    artifacts = list(out.glob("*.json"))
    assert artifacts
    payload = json.loads(artifacts[0].read_text())
    assert payload["schema_version"] == ARENA_RUN_SCHEMA_VERSION
    assert "buyer_score" in payload and "seller_score" in payload


def test_run_arena_from_paths_round_trips(tmp_path):
    _plan(tmp_path, participants=("alice", "bob"))
    db = tmp_path / "ratings.db"

    summary = run_arena_from_paths(
        plan_path=tmp_path / "plan.json",
        scenario=_scenario(),
        store_path=db,
    )

    assert summary.matchups_executed > 0
    reopened = RatingStore(db)
    assert reopened.match_count() == summary.matchups_total


def test_arena_run_cli(tmp_path, capsys):
    _plan(tmp_path, participants=("alice", "bob", "carol"))
    db = tmp_path / "ratings.db"

    code = main(
        [
            "arena-run",
            "--plan", str(tmp_path / "plan.json"),
            "--store", str(db),
            "--output-dir", str(tmp_path / "matches"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "completed"
    assert payload["matchups_executed"] == payload["matchups_total"]
    assert db.exists()
