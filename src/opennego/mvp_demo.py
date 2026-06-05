"""One-command no-key MVP demo orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from opennego.evolution import write_strategy_candidate
from opennego.learning import write_battle_report
from opennego.report import write_demo_report
from opennego.runner import RunRecord, run_experiment_config


@dataclass(frozen=True)
class MvpDemoSummary:
    name: str
    output_dir: str
    benchmark_completed: int
    benchmark_failed: int
    learning_input_dir: str
    battle_report: str
    strategy_candidate: str
    html_report: str


def run_mvp_demo(
    *,
    output_dir: str | Path = "runs/mvp_demo",
    report_path: str | Path | None = None,
    config_path: str | Path = "configs/real_market_demo.yaml",
    learning_tool_regime: str = "no_tools",
    user_role: str = "buyer",
    opponent_profile_id: str = "seller_hardline_anchor_v1",
) -> MvpDemoSummary:
    """Run benchmark, policy learning, and HTML report generation."""

    output = Path(output_dir)
    summary = run_experiment_config(config_path, output_dir=output)
    learning_run = _select_learning_run(summary.runs, learning_tool_regime)
    battle_report = output / "battle_report.json"
    strategy_candidate = output / "strategy_candidate.json"
    html_report = (
        Path(report_path)
        if report_path is not None
        else output / "opennego_mvp_demo.html"
    )

    write_battle_report(
        learning_run.output_dir,
        battle_report,
        user_role=user_role,
        opponent_profile_id=opponent_profile_id,
    )
    write_strategy_candidate(
        battle_report,
        strategy_candidate,
        parent_strategy_id=f"{user_role}_baseline",
        iteration=1,
    )
    write_demo_report(output, html_report)

    return MvpDemoSummary(
        name="opennego_mvp_demo",
        output_dir=str(output),
        benchmark_completed=summary.completed,
        benchmark_failed=summary.failed,
        learning_input_dir=learning_run.output_dir,
        battle_report=str(battle_report),
        strategy_candidate=str(strategy_candidate),
        html_report=str(html_report),
    )


def _select_learning_run(
    records: Sequence[RunRecord],
    tool_regime: str,
) -> RunRecord:
    for record in records:
        if record.status == "completed" and f"-{tool_regime}-" in record.run_id:
            return record
    completed = [record for record in records if record.status == "completed"]
    if completed:
        return completed[0]
    raise ValueError("MVP demo requires at least one completed benchmark run")
