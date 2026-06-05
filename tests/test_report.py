from opennego.report import write_demo_report
from opennego.runner import run_experiment_config
from opennego.learning import write_battle_report


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
    assert "OpenNego" in html
    assert "Leaderboard Preview" in html
    assert "Trace Replay" in html
    assert "Market Reference" in html
    assert "Strategy Marketplace" in html
    assert "Hardline Anchor Seller" in html
    assert 'href="#attempts"' not in html
    assert not any(line.rstrip() != line for line in html.splitlines())


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

    output = write_demo_report(runs_dir, report_path)
    html = output.read_text()

    assert "Training / Prompt Optimization" in html
    assert "buyer_overpaid_market" in html
    assert "The accepted price $608.00 is more than 5% above the market reference $575.00." in html
    assert 'href="#training"' in html
    assert 'href="#marketplace"' in html
