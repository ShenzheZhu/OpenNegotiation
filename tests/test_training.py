import json
from pathlib import Path

from opennego.cli import main
from opennego.evolution import (
    STRATEGY_COMPARISON_SCHEMA_VERSION,
    STRATEGY_EVOLUTION_SCHEMA_VERSION,
)
from opennego.sparring import SPARRING_EXECUTION_MODE, SPARRING_SUITE_SCHEMA_VERSION
from opennego.training import TRAINING_LOOP_SCHEMA_VERSION, run_training_loop


def test_training_loop_writes_candidate_rerun_and_comparison(tmp_path):
    output_dir = tmp_path / "training"

    summary = run_training_loop(
        output_dir=output_dir,
        opponent_profile_ids=("seller_hardline_anchor_v1",),
        parent_strategy_id="buyer_baseline",
    )

    payload = json.loads((output_dir / "training_loop.json").read_text())
    candidate = json.loads((output_dir / "strategy_candidate.json").read_text())
    comparison = json.loads((output_dir / "strategy_comparison.json").read_text())
    baseline = json.loads((output_dir / "baseline" / "sparring_suite.json").read_text())
    rerun = json.loads((output_dir / "rerun" / "sparring_suite.json").read_text())

    assert summary.schema_version == TRAINING_LOOP_SCHEMA_VERSION
    assert summary.status == "completed"
    assert summary.selected_profile_id == "seller_hardline_anchor_v1"
    assert payload["schema_version"] == TRAINING_LOOP_SCHEMA_VERSION
    assert payload["selected_battle_report"].endswith("battle_report.json")
    assert payload["baseline_completed"] == 1
    assert payload["rerun_completed"] == 1
    assert payload["shared_runtime_contract"] == {
        "baseline_execution_mode": SPARRING_EXECUTION_MODE,
        "rerun_execution_mode": SPARRING_EXECUTION_MODE,
        "sparring_execution_mode": SPARRING_EXECUTION_MODE,
        "orchestrator": "opennego.sparring.run_sparring_suite",
        "separate_prompt_simulator": False,
        "artifact_backed": True,
    }
    assert candidate["schema_version"] == STRATEGY_EVOLUTION_SCHEMA_VERSION
    assert candidate["candidate_id"] == "buyer_baseline-iter-1"
    assert comparison["schema_version"] == STRATEGY_COMPARISON_SCHEMA_VERSION
    assert comparison["before_battle_report"] == payload["selected_battle_report"]
    assert comparison["after_battle_report"] == payload["rerun_battle_report"]
    assert baseline["schema_version"] == SPARRING_SUITE_SCHEMA_VERSION
    assert rerun["schema_version"] == SPARRING_SUITE_SCHEMA_VERSION
    assert rerun["user_strategy_candidate_id"] == "buyer_baseline-iter-1"
    assert Path(payload["artifact_path"]).exists()


def test_train_cli_runs_no_key_training_loop(tmp_path, capsys):
    output_dir = tmp_path / "cli_training"

    status = main(
        [
            "train",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
            "--parent-strategy-id",
            "buyer_baseline",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 0
    assert payload["schema_version"] == TRAINING_LOOP_SCHEMA_VERSION
    assert payload["status"] == "completed"
    assert payload["artifact_path"] == str(output_dir / "training_loop.json")
    assert (output_dir / "strategy_candidate.json").exists()
    assert (output_dir / "strategy_comparison.json").exists()


def test_train_cli_reports_profile_errors_without_traceback(tmp_path, capsys):
    status = main(
        [
            "train",
            "--output-dir",
            str(tmp_path / "bad_training"),
            "--opponent-profile",
            "buyer_budget_probe_v1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 2
    assert "expected seller profile" in payload["error"]
