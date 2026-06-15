import json
import pytest
from pathlib import Path

from opennego.cli import main
from opennego.evolution import (
    STRATEGY_COMPARISON_SCHEMA_VERSION,
    STRATEGY_EVOLUTION_SCHEMA_VERSION,
)
from opennego.sparring import SPARRING_EXECUTION_MODE, SPARRING_SUITE_SCHEMA_VERSION
from opennego.strategy_config import STRATEGY_CONFIG_SCHEMA_VERSION
from opennego.runner import run_experiment_config
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
    config = json.loads((output_dir / "strategy_config.json").read_text())
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
    assert config["schema_version"] == STRATEGY_CONFIG_SCHEMA_VERSION
    assert config["source_candidate_id"] == "buyer_baseline-iter-1"
    assert config["metadata"]["strategy_config_version"] == STRATEGY_CONFIG_SCHEMA_VERSION
    assert payload["strategy_config"] == str(output_dir / "strategy_config.json")
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
    assert (output_dir / "strategy_config.json").exists()
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


def test_split_opponent_roster_is_deterministic_with_safety_in_both():
    from opennego.schema import Role
    from opennego.training import split_opponent_roster

    train_a, heldout_a = split_opponent_roster(
        registry_path="examples/data/npc_strategies.json",
        user_role=Role.BUYER,
        seed=7,
    )
    train_b, heldout_b = split_opponent_roster(
        registry_path="examples/data/npc_strategies.json",
        user_role=Role.BUYER,
        seed=7,
    )

    assert (train_a, heldout_a) == (train_b, heldout_b)
    # Safety/scam seller profile must appear in both sets.
    assert "seller_scam_offplatform_v1" in train_a
    assert "seller_scam_offplatform_v1" in heldout_a
    # Non-safety profiles are partitioned, not duplicated.
    non_safety_train = set(train_a) - {"seller_scam_offplatform_v1"}
    non_safety_heldout = set(heldout_a) - {"seller_scam_offplatform_v1"}
    assert non_safety_train.isdisjoint(non_safety_heldout)


def test_training_loop_reports_generalization(tmp_path):
    output_dir = tmp_path / "holdout_training"

    summary = run_training_loop(
        output_dir=output_dir,
        parent_strategy_id="buyer_baseline",
        holdout_validation=True,
        holdout_seed=7,
    )

    assert summary.generalization is not None
    verdict = summary.generalization["verdict"]
    assert verdict in {"improved", "train_only", "regressed"}
    assert summary.generalization["train"]["profile_count"] >= 1
    assert summary.generalization["held_out"]["profile_count"] >= 1
    candidate = json.loads((output_dir / "strategy_candidate.json").read_text())
    assert candidate["metadata"]["generalization_verdict"] == verdict
    payload = json.loads((output_dir / "training_loop.json").read_text())
    assert payload["generalization"]["verdict"] == verdict


def test_apply_strategy_refuses_train_only_without_override(tmp_path):
    from opennego.artifacts import write_json
    from opennego.evolution import generate_strategy_candidate, write_strategy_candidate
    from opennego.strategy_config import StrategyConfigError, write_strategy_config

    runs_dir = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = runs_dir / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"
    from opennego.learning import write_battle_report

    report_path = tmp_path / "battle_report.json"
    write_battle_report(run_dir, report_path, user_role="buyer",
                        opponent_profile_id="seller_hardline_anchor_v1")
    candidate_path = tmp_path / "candidate.json"
    write_strategy_candidate(report_path, candidate_path, parent_strategy_id="buyer_baseline")

    # Stamp a train_only verdict like held-out validation would.
    candidate = json.loads(candidate_path.read_text())
    candidate["metadata"]["generalization_verdict"] = "train_only"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n")

    config_path = tmp_path / "config.json"
    with pytest.raises(StrategyConfigError, match="train_only"):
        write_strategy_config(candidate_path, config_path)

    # Override applies it.
    written = write_strategy_config(candidate_path, config_path, allow_train_only=True)
    assert written.exists()
