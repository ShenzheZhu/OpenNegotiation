import json

from opennego.cli import main
from opennego.leaderboard import LEADERBOARD_SCHEMA_VERSION
from opennego.mvp_demo import run_mvp_demo


def test_run_mvp_demo_generates_benchmark_learning_and_report(tmp_path):
    output_dir = tmp_path / "mvp"
    report_path = tmp_path / "opennego_mvp_demo.html"

    summary = run_mvp_demo(output_dir=output_dir, report_path=report_path)

    assert summary.name == "opennego_mvp_demo"
    assert summary.benchmark_completed == 3
    assert summary.benchmark_failed == 0
    assert (output_dir / "leaderboard_summary.json").exists()
    assert (output_dir / "battle_report.json").exists()
    assert (output_dir / "strategy_candidate.json").exists()
    assert report_path.exists()

    leaderboard = json.loads((output_dir / "leaderboard_summary.json").read_text())
    battle_report = json.loads((output_dir / "battle_report.json").read_text())
    candidate = json.loads((output_dir / "strategy_candidate.json").read_text())
    html = report_path.read_text()

    assert summary.leaderboard_summary == str(output_dir / "leaderboard_summary.json")
    assert leaderboard["schema_version"] == LEADERBOARD_SCHEMA_VERSION
    assert leaderboard["run_count"] == 3
    assert leaderboard["participant_summaries"]
    assert battle_report["opponent_profile_id"] == "seller_hardline_anchor_v1"
    assert candidate["parent_strategy_id"] == "buyer_baseline"
    assert "buyer_overpaid_market" in candidate["applied_lesson_ids"]
    lesson_ids = {lesson["id"] for lesson in battle_report["lessons"]}
    assert "buyer_overpaid_market" in lesson_ids
    assert "Leaderboard Preview" in html
    assert "Training / Prompt Optimization" in html
    assert "Strategy Marketplace" in html
    assert "Hardline Anchor Seller" in html


def test_mvp_demo_cli_prints_artifact_paths(tmp_path, capsys):
    output_dir = tmp_path / "cli_mvp"
    report_path = tmp_path / "cli_mvp.html"

    status = main(
        [
            "mvp-demo",
            "--output-dir",
            str(output_dir),
            "--report",
            str(report_path),
        ]
    )
    stdout = capsys.readouterr().out

    payload = json.loads(stdout)
    assert status == 0
    assert payload["benchmark_completed"] == 3
    assert payload["benchmark_failed"] == 0
    assert payload["leaderboard_summary"] == str(
        output_dir / "leaderboard_summary.json"
    )
    assert payload["battle_report"] == str(output_dir / "battle_report.json")
    assert payload["strategy_candidate"] == str(output_dir / "strategy_candidate.json")
    assert payload["html_report"] == str(report_path)
    assert (output_dir / "leaderboard_summary.json").exists()
    assert report_path.exists()
