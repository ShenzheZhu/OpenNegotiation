import json
from pathlib import Path

import pytest

from opennego.cli import main
from opennego.sparring import (
    SPARRING_EXECUTION_MODE,
    SPARRING_SUITE_SCHEMA_VERSION,
    run_sparring_suite,
)


def test_run_sparring_suite_writes_profile_reports(tmp_path):
    output_dir = tmp_path / "sparring"

    summary = run_sparring_suite(
        output_dir=output_dir,
        opponent_profile_ids=(
            "seller_hardline_anchor_v1",
            "seller_hidden_fees_v1",
        ),
    )

    payload = json.loads((output_dir / "sparring_suite.json").read_text())
    profile_ids = {result.profile_id for result in summary.results}

    assert summary.schema_version == SPARRING_SUITE_SCHEMA_VERSION
    assert summary.execution_mode == SPARRING_EXECUTION_MODE
    assert summary.completed == 2
    assert summary.failed == 0
    assert profile_ids == {"seller_hardline_anchor_v1", "seller_hidden_fees_v1"}
    assert payload["schema_version"] == SPARRING_SUITE_SCHEMA_VERSION
    assert payload["completed"] == 2

    for result in summary.results:
        battle_report_path = (
            output_dir / "profiles" / result.profile_id / "battle_report.json"
        )
        learning_dir = result.learning_input_dir
        assert learning_dir is not None
        manifest = json.loads((Path(learning_dir) / "manifest.json").read_text())
        trace = (Path(learning_dir) / "trace.jsonl").read_text()

        assert result.status == "completed"
        assert result.benchmark_completed == 3
        assert result.benchmark_failed == 0
        assert result.battle_report == str(battle_report_path)
        assert battle_report_path.exists()
        assert "buyer_overpaid_market" in result.lesson_ids
        assert manifest["agents"]["seller"]["profile_id"] == result.profile_id
        assert f"npc_seller:{result.profile_id}" in trace


def test_sparring_suite_rejects_wrong_role_profile(tmp_path):
    with pytest.raises(ValueError, match="expected seller profile"):
        run_sparring_suite(
            output_dir=tmp_path / "sparring",
            user_role="buyer",
            opponent_profile_ids=("buyer_budget_probe_v1",),
        )


def test_sparring_suite_supports_seller_user_against_buyer_profile(tmp_path):
    output_dir = tmp_path / "seller_sparring"

    summary = run_sparring_suite(
        output_dir=output_dir,
        user_role="seller",
        opponent_profile_ids=("buyer_budget_probe_v1",),
    )
    result = summary.results[0]
    assert result.learning_input_dir is not None
    manifest = json.loads(
        (Path(result.learning_input_dir) / "manifest.json").read_text()
    )
    trace = (Path(result.learning_input_dir) / "trace.jsonl").read_text()

    assert summary.completed == 1
    assert summary.failed == 0
    assert summary.user_role.value == "seller"
    assert result.profile_id == "buyer_budget_probe_v1"
    assert manifest["agents"]["buyer"]["profile_id"] == "buyer_budget_probe_v1"
    assert manifest["agents"]["seller"]["kind"] == "user_seller"
    assert "npc_buyer:buyer_budget_probe_v1" in trace


def test_spar_cli_prints_suite_artifact(tmp_path, capsys):
    output_dir = tmp_path / "cli_spar"

    status = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert status == 0
    assert payload["schema_version"] == SPARRING_SUITE_SCHEMA_VERSION
    assert payload["completed"] == 1
    assert payload["failed"] == 0
    assert payload["artifact_path"] == str(output_dir / "sparring_suite.json")
    assert (output_dir / "sparring_suite.json").exists()


def test_spar_cli_rejects_wrong_role_profile(tmp_path, capsys):
    status = main(
        [
            "spar",
            "--output-dir",
            str(tmp_path / "cli_spar"),
            "--opponent-profile",
            "buyer_budget_probe_v1",
        ]
    )
    stdout = capsys.readouterr().out

    assert status == 2
    assert "expected seller profile" in stdout
