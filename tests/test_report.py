from opennego.report import write_demo_report
from opennego.runner import run_experiment_config


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
