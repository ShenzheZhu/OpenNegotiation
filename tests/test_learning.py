import json

from opennego.cli import main
from opennego.coaching import BATTLE_REPORT_V2_SCHEMA_VERSION
from opennego.learning import (
    POLICY_LEARNING_SCHEMA_VERSION,
    generate_battle_report,
    registry_listing,
    write_battle_report,
)
from opennego.runner import run_experiment_config


def test_strategy_registry_lists_seller_npcs():
    listing = registry_listing("examples/data/npc_strategies.json", role="seller")

    profile_ids = {profile["id"] for profile in listing["profiles"]}
    assert listing["schema_version"] == POLICY_LEARNING_SCHEMA_VERSION
    assert "seller_hardline_anchor_v1" in profile_ids
    assert "seller_hidden_fees_v1" in profile_ids
    assert "buyer_budget_probe_v1" not in profile_ids


def test_policy_learning_report_extracts_trace_grounded_lessons(tmp_path):
    runs_dir = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = runs_dir / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"

    report = generate_battle_report(
        run_dir,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )

    lesson_ids = {lesson.id for lesson in report.lessons}
    assert report.schema_version == BATTLE_REPORT_V2_SCHEMA_VERSION
    assert report.user_role.value == "buyer"
    assert report.opponent_profile_id == "seller_hardline_anchor_v1"
    assert report.outcome == "deal"
    assert "buyer_overpaid_market" in lesson_ids
    assert report.lessons[0].evidence
    assert "strategy layer" in report.suggested_strategy_prompt
    assert report.metadata["base_prompt_fixed"] is True


def test_write_battle_report_writes_json_artifact(tmp_path):
    runs_dir = tmp_path / "runs"
    output_path = tmp_path / "battle_report.json"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = runs_dir / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"

    written = write_battle_report(
        run_dir,
        output_path,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    payload = json.loads(written.read_text())

    assert written == output_path
    assert payload["schema_version"] == BATTLE_REPORT_V2_SCHEMA_VERSION
    assert payload["run_id"] == "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"
    assert payload["lessons"]
    assert payload["artifacts"]["trace"].endswith("trace.jsonl")


def test_policy_learning_does_not_flag_missing_transaction_layer(tmp_path):
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "opennego.experiment.v1",
                "name": "learning_no_transaction",
                "output_dir": str(runs_dir),
                "resume": False,
                "fail_fast": True,
                "seeds": [3],
                "agents": {
                    "buyer": {"kind": "tool_aware_buyer"},
                    "seller": {"kind": "scripted_seller"},
                },
                "scenarios": [
                    {
                        "id": "iphone_14_pro_128gb_unlocked_good",
                        "products_file": "examples/data/real_market_products.json",
                        "product_index": 0,
                        "max_turns": 8,
                    }
                ],
                "tool_regimes": [{"id": "no_tools", "tools": []}],
            },
            indent=2,
        )
        + "\n"
    )
    run_experiment_config(config_path)
    run_dir = runs_dir / "learning_no_transaction-iphone_14_pro_128gb_unlocked_good-no_tools-seed-3"

    report = generate_battle_report(
        run_dir,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )

    lesson_ids = {lesson.id for lesson in report.lessons}
    assert "transaction_risk_ignored" not in lesson_ids


def test_policy_learning_cli_commands(tmp_path, capsys):
    runs_dir = tmp_path / "runs"
    output_path = tmp_path / "battle_report.json"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = runs_dir / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"

    strategies_status = main(["strategies", "--role", "seller"])
    strategies_stdout = capsys.readouterr().out
    learn_status = main(
        [
            "learn",
            "--input-dir",
            str(run_dir),
            "--output",
            str(output_path),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
        ]
    )
    learn_stdout = capsys.readouterr().out

    assert strategies_status == 0
    assert "seller_hardline_anchor_v1" in strategies_stdout
    assert learn_status == 0
    assert str(output_path) in learn_stdout
    assert output_path.exists()
