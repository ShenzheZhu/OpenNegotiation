import json

from opennego.arena import ARENA_PLAN_SCHEMA_VERSION, build_arena_plan, write_arena_plan
from opennego.cli import main


def test_arena_plan_writes_reciprocal_buyer_seller_matchups(tmp_path):
    output_path = tmp_path / "arena_plan.json"

    plan = write_arena_plan(
        output_path,
        participants=("alpha", "beta", "gamma"),
        scenario_ids=("iphone_market",),
        seeds=(7, 11),
    )
    payload = json.loads(output_path.read_text())
    pairs = {
        (
            item["scenario_id"],
            item["seed"],
            item["buyer_participant_id"],
            item["seller_participant_id"],
        )
        for item in payload["matchups"]
    }

    assert plan.schema_version == ARENA_PLAN_SCHEMA_VERSION
    assert payload["schema_version"] == ARENA_PLAN_SCHEMA_VERSION
    assert payload["status"] == "planned"
    assert payload["participants"] == ["alpha", "beta", "gamma"]
    assert payload["scenario_ids"] == ["iphone_market"]
    assert payload["seeds"] == [7, 11]
    assert payload["matchup_count"] == 12
    assert payload["reciprocal_group_count"] == 6
    assert payload["required_role_coverage"] == {
        "alpha": ["buyer", "seller"],
        "beta": ["buyer", "seller"],
        "gamma": ["buyer", "seller"],
    }
    assert ("iphone_market", 7, "alpha", "beta") in pairs
    assert ("iphone_market", 7, "beta", "alpha") in pairs
    assert payload["ranking_methodology"]["primary"]["name"] == "deterministic_scorecard"
    assert payload["ranking_methodology"]["primary"]["status"] == "implemented"
    assert payload["ranking_methodology"]["arena_optional"]["name"] == (
        "elo_or_bradley_terry"
    )
    assert payload["ranking_methodology"]["arena_optional"]["status"] == (
        "planned_optional_layer"
    )


def test_arena_plan_cli_prints_summary(tmp_path, capsys):
    output_path = tmp_path / "cli_arena_plan.json"

    status = main(
        [
            "arena-plan",
            "--participant",
            "alpha",
            "--participant",
            "beta",
            "--scenario-id",
            "iphone_market",
            "--seed",
            "7",
            "--output",
            str(output_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 0
    assert payload["schema_version"] == ARENA_PLAN_SCHEMA_VERSION
    assert payload["matchup_count"] == 2
    assert payload["reciprocal_group_count"] == 1
    assert payload["output_path"] == str(output_path)
    assert output_path.exists()


def test_arena_plan_rejects_duplicate_participants(tmp_path, capsys):
    status = main(
        [
            "arena-plan",
            "--participant",
            "alpha",
            "--participant",
            "alpha",
            "--output",
            str(tmp_path / "bad.json"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 2
    assert "duplicate id" in payload["error"]


def test_arena_plan_self_play_is_diagnostic():
    plan = build_arena_plan(
        participants=("alpha", "beta"),
        include_self_play=True,
    )

    assert plan.matchup_count == 4
    assert any("Self-play rows are diagnostic" in warning for warning in plan.warnings)
