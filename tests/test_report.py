from opennego.report import write_demo_report
from opennego.runner import run_experiment_config
from opennego.learning import write_battle_report
from opennego.evolution import write_strategy_candidate
from opennego.leaderboard import LEADERBOARD_SCHEMA_VERSION, write_leaderboard


def test_write_demo_report_from_real_market_demo_config(tmp_path):
    runs_dir = tmp_path / "runs"
    report_path = tmp_path / "opennego_demo.html"

    summary = run_experiment_config(
        "configs/real_market_demo.yaml",
        output_dir=runs_dir,
    )
    output = write_demo_report(runs_dir, report_path)

    html = output.read_text()
    assert summary.total_runs == 3
    assert summary.completed == 3
    assert "OpenNegotiation" in html
    assert "Leaderboard Preview" in html
    assert "Trace Replay" in html
    assert "Market Reference" in html
    assert "Strategy Marketplace" in html
    assert "Hardline Anchor Seller" in html
    assert "Leaderboard source: run artifacts fallback." in html
    assert 'href="#attempts"' not in html
    assert not any(line.rstrip() != line for line in html.splitlines())


def test_write_demo_report_uses_leaderboard_summary_when_available(tmp_path):
    runs_dir = tmp_path / "runs"
    report_path = tmp_path / "opennego_demo.html"

    run_experiment_config(
        "configs/real_market_demo.yaml",
        output_dir=runs_dir,
    )
    write_leaderboard(runs_dir, runs_dir / "leaderboard_summary.json")

    output = write_demo_report(runs_dir, report_path)
    html = output.read_text()

    assert f"Leaderboard artifact {LEADERBOARD_SCHEMA_VERSION}" in html
    assert "Participant Coverage" in html
    assert "tool_aware_buyer:tool_aware_buyer" in html
    assert "scripted_seller:scripted_seller" in html
    assert "0.50" in html


def test_write_demo_report_falls_back_for_malformed_leaderboard_summary(tmp_path):
    runs_dir = tmp_path / "runs"
    report_path = tmp_path / "opennego_demo.html"

    run_experiment_config(
        "configs/real_market_demo.yaml",
        output_dir=runs_dir,
    )
    (runs_dir / "leaderboard_summary.json").write_text(
        '{"schema_version": "wrong"}\n'
    )

    output = write_demo_report(runs_dir, report_path)
    html = output.read_text()

    assert "Leaderboard source: run artifacts fallback." in html
    assert "Participant Coverage" not in html


def test_write_demo_report_includes_policy_learning_when_report_exists(tmp_path):
    runs_dir = tmp_path / "runs"
    report_path = tmp_path / "opennego_mvp.html"

    run_experiment_config(
        "configs/real_market_demo.yaml",
        output_dir=runs_dir,
    )
    run_dir = runs_dir / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"
    write_battle_report(
        run_dir,
        runs_dir / "battle_report.json",
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    write_strategy_candidate(
        runs_dir / "battle_report.json",
        runs_dir / "strategy_candidate.json",
        parent_strategy_id="buyer_baseline",
    )

    output = write_demo_report(runs_dir, report_path)
    html = output.read_text()

    assert "Training / Prompt Optimization" in html
    assert "Strategy Candidate" in html
    assert "buyer_baseline-iter-1" in html
    assert "opennego spar --user-role buyer" in html
    assert "buyer_overpaid_market" in html
    assert "The accepted price $608.00 is more than 5% above the market reference $575.00." in html
    assert 'href="#training"' in html
    assert 'href="#marketplace"' in html
