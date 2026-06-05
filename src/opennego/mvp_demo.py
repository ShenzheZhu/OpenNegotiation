"""One-command no-key MVP demo orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import read_json, write_json
from opennego.evolution import (
    STRATEGY_EVOLUTION_SCHEMA_VERSION,
    write_strategy_candidate,
)
from opennego.leaderboard import LEADERBOARD_SCHEMA_VERSION, write_leaderboard
from opennego.learning import POLICY_LEARNING_SCHEMA_VERSION, write_battle_report
from opennego.report import write_demo_report
from opennego.runner import RunRecord, run_experiment_config

MVP_DEMO_BUNDLE_SCHEMA_VERSION = "opennego.mvp_demo_bundle.v1"


@dataclass(frozen=True)
class MvpDemoSummary:
    name: str
    output_dir: str
    benchmark_completed: int
    benchmark_failed: int
    learning_input_dir: str
    leaderboard_summary: str
    battle_report: str
    strategy_candidate: str
    html_report: str
    bundle_manifest: str


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
    bundle_manifest = output / "mvp_demo_manifest.json"
    leaderboard_summary = output / "leaderboard_summary.json"
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
    write_leaderboard(output, leaderboard_summary)
    write_strategy_candidate(
        battle_report,
        strategy_candidate,
        parent_strategy_id=f"{user_role}_baseline",
        iteration=1,
    )
    write_demo_report(output, html_report)
    _write_bundle_manifest(
        bundle_manifest,
        output_dir=output,
        benchmark_completed=summary.completed,
        benchmark_failed=summary.failed,
        learning_run=learning_run,
        leaderboard_summary=leaderboard_summary,
        battle_report=battle_report,
        strategy_candidate=strategy_candidate,
        html_report=html_report,
    )

    return MvpDemoSummary(
        name="opennego_mvp_demo",
        output_dir=str(output),
        benchmark_completed=summary.completed,
        benchmark_failed=summary.failed,
        learning_input_dir=learning_run.output_dir,
        leaderboard_summary=str(leaderboard_summary),
        battle_report=str(battle_report),
        strategy_candidate=str(strategy_candidate),
        html_report=str(html_report),
        bundle_manifest=str(bundle_manifest),
    )


def _write_bundle_manifest(
    output_path: Path,
    *,
    output_dir: Path,
    benchmark_completed: int,
    benchmark_failed: int,
    learning_run: RunRecord,
    leaderboard_summary: Path,
    battle_report: Path,
    strategy_candidate: Path,
    html_report: Path,
) -> Path:
    manifest = {
        "schema_version": MVP_DEMO_BUNDLE_SCHEMA_VERSION,
        "name": "opennego_mvp_demo",
        "output_dir": str(output_dir),
        "benchmark": {
            "completed": benchmark_completed,
            "failed": benchmark_failed,
            "learning_input_dir": learning_run.output_dir,
            "learning_run_id": learning_run.run_id,
        },
        "artifacts": {
            "leaderboard_summary": str(leaderboard_summary),
            "battle_report": str(battle_report),
            "strategy_candidate": str(strategy_candidate),
            "html_report": str(html_report),
        },
        "artifact_schema_versions": {
            "leaderboard_summary": _artifact_schema_version(leaderboard_summary),
            "battle_report": _artifact_schema_version(battle_report),
            "strategy_candidate": _artifact_schema_version(strategy_candidate),
        },
        "expected_schema_versions": {
            "leaderboard_summary": LEADERBOARD_SCHEMA_VERSION,
            "battle_report": POLICY_LEARNING_SCHEMA_VERSION,
            "strategy_candidate": STRATEGY_EVOLUTION_SCHEMA_VERSION,
        },
        "workflow_steps": (
            "benchmark",
            "leaderboard",
            "policy_learning",
            "strategy_evolution",
            "html_report",
        ),
    }
    write_json(output_path, manifest)
    return output_path


def _artifact_schema_version(path: Path) -> str:
    try:
        payload: Mapping[str, Any] = read_json(path)
    except (OSError, ValueError):
        return "missing"
    value = payload.get("schema_version")
    return str(value or "unknown")


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
