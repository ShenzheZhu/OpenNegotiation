import json
from pathlib import Path

from opennego.cli import main
from opennego.leaderboard import LEADERBOARD_SCHEMA_VERSION, build_leaderboard
from opennego.role_swap import ROLE_SWAP_SCHEMA_VERSION, run_role_swap_benchmark


def test_role_swap_benchmark_writes_combined_leaderboard(tmp_path):
    output_dir = tmp_path / "role_swap"

    summary = run_role_swap_benchmark(
        output_dir=output_dir,
        participant_id="baseline_strategy",
    )
    payload = json.loads((output_dir / "role_swap_summary.json").read_text())
    leaderboard_payload = json.loads(
        (output_dir / "leaderboard_summary.json").read_text()
    )
    leaderboard = build_leaderboard(output_dir / "combined_runs")
    participant = _participant(leaderboard, "baseline_strategy")

    assert summary.schema_version == ROLE_SWAP_SCHEMA_VERSION
    assert summary.status == "completed"
    assert summary.completed == 4
    assert summary.failed == 0
    assert summary.participant_roles == ("buyer", "seller")
    assert summary.participant_role_coverage == 1.0
    assert payload["schema_version"] == ROLE_SWAP_SCHEMA_VERSION
    assert payload["participant_id"] == "baseline_strategy"
    assert leaderboard_payload["schema_version"] == LEADERBOARD_SCHEMA_VERSION
    assert leaderboard_payload["run_count"] == 4
    assert participant.roles == ("buyer", "seller")
    assert participant.role_coverage == 1.0
    assert _track(leaderboard, "buyer", "baseline_strategy").run_count == 2
    assert _track(leaderboard, "seller", "baseline_strategy").run_count == 2
    assert Path(payload["buyer_role_config"]).exists()
    assert Path(payload["seller_role_config"]).exists()


def test_role_swap_cli_prints_summary(tmp_path, capsys):
    output_dir = tmp_path / "cli_role_swap"

    status = main(
        [
            "role-swap",
            "--output-dir",
            str(output_dir),
            "--participant-id",
            "baseline_strategy",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 0
    assert payload["schema_version"] == ROLE_SWAP_SCHEMA_VERSION
    assert payload["participant_role_coverage"] == 1.0
    assert payload["leaderboard_summary"] == str(output_dir / "leaderboard_summary.json")
    assert (output_dir / "combined_runs").exists()


def _participant(summary, participant_id):
    for entry in summary.participant_summaries:
        if entry.participant_id == participant_id:
            return entry
    raise AssertionError(f"missing participant summary for {participant_id}")


def _track(summary, role, participant_id):
    for entry in summary.role_tracks:
        if entry.role == role and entry.participant_id == participant_id:
            return entry
    raise AssertionError(f"missing {role} role track for {participant_id}")
