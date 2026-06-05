import json

import pytest

from opennego.cli import main
from opennego.evolution import (
    STRATEGY_COMPARISON_SCHEMA_VERSION,
    STRATEGY_EVOLUTION_SCHEMA_VERSION,
    StrategyEvolutionError,
    generate_strategy_candidate,
    generate_strategy_comparison,
    write_strategy_candidate,
)
from opennego.learning import write_battle_report
from opennego.runner import run_experiment_config


def test_strategy_candidate_turns_battle_report_into_versioned_patch(tmp_path):
    battle_report = _write_real_market_battle_report(tmp_path, "no_tools")

    candidate = generate_strategy_candidate(
        battle_report,
        parent_strategy_id="buyer_baseline",
        iteration=2,
    )

    assert candidate.schema_version == STRATEGY_EVOLUTION_SCHEMA_VERSION
    assert candidate.candidate_id == "buyer_baseline-iter-2"
    assert candidate.parent_strategy_id == "buyer_baseline"
    assert candidate.user_role.value == "buyer"
    assert candidate.opponent_profile_id == "seller_hardline_anchor_v1"
    assert "buyer_overpaid_market" in candidate.applied_lesson_ids
    assert candidate.applied_patches
    assert candidate.metadata["base_prompt_fixed"] is True
    assert "opennego spar --user-role buyer" in candidate.evaluation_plan["rerun_command"]


def test_write_strategy_candidate_writes_json_artifact(tmp_path):
    battle_report = _write_real_market_battle_report(tmp_path, "no_tools")
    output_path = tmp_path / "strategy_candidate.json"

    written = write_strategy_candidate(
        battle_report,
        output_path,
        parent_strategy_id="buyer_baseline",
        iteration=1,
    )
    payload = json.loads(written.read_text())

    assert written == output_path
    assert payload["schema_version"] == STRATEGY_EVOLUTION_SCHEMA_VERSION
    assert payload["candidate_id"] == "buyer_baseline-iter-1"
    assert payload["source_battle_report"] == str(battle_report)


def test_strategy_comparison_scores_before_after_reports(tmp_path):
    before = _write_real_market_battle_report(tmp_path, "no_tools")
    after = _write_real_market_battle_report(tmp_path, "buyer_private_market_search")

    comparison = generate_strategy_comparison(before, after)

    assert comparison.schema_version == STRATEGY_COMPARISON_SCHEMA_VERSION
    assert comparison.status == "improved"
    assert comparison.score_delta > 0
    assert comparison.user_price_delta is not None
    assert comparison.user_price_delta > 0
    assert "buyer_overpaid_market" in comparison.resolved_lesson_ids


def test_strategy_evolution_cli_commands(tmp_path, capsys):
    before = _write_real_market_battle_report(tmp_path, "no_tools")
    after = _write_real_market_battle_report(tmp_path, "buyer_private_market_search")
    candidate_path = tmp_path / "candidate.json"
    comparison_path = tmp_path / "comparison.json"

    evolve_status = main(
        [
            "evolve",
            "--battle-report",
            str(before),
            "--output",
            str(candidate_path),
            "--parent-strategy-id",
            "buyer_baseline",
        ]
    )
    evolve_stdout = capsys.readouterr().out
    compare_status = main(
        [
            "compare",
            "--before",
            str(before),
            "--after",
            str(after),
            "--output",
            str(comparison_path),
        ]
    )
    compare_stdout = capsys.readouterr().out

    assert evolve_status == 0
    assert str(candidate_path) in evolve_stdout
    assert candidate_path.exists()
    assert compare_status == 0
    assert str(comparison_path) in compare_stdout
    assert comparison_path.exists()


def test_strategy_evolution_rejects_malformed_policy_schema(tmp_path):
    bad_report = tmp_path / "bad_battle_report.json"
    bad_report.write_text(json.dumps({"schema_version": "wrong"}) + "\n")

    with pytest.raises(StrategyEvolutionError, match="expected opennego.policy_learning.v1"):
        generate_strategy_candidate(bad_report)

    status = main(
        [
            "evolve",
            "--battle-report",
            str(bad_report),
            "--output",
            str(tmp_path / "candidate.json"),
        ]
    )
    assert status == 2


def _write_real_market_battle_report(tmp_path, tool_regime):
    runs_dir = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = (
        runs_dir
        / f"real_market_demo-iphone_14_pro_128gb_unlocked_good-{tool_regime}-seed-13"
    )
    report_path = tmp_path / f"{tool_regime}_battle_report.json"
    write_battle_report(
        run_dir,
        report_path,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    return report_path
