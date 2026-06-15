"""One-command local demo orchestration."""

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
from opennego.coaching import BATTLE_REPORT_V2_SCHEMA_VERSION
from opennego.learning import write_battle_report
from opennego.report import write_demo_report
from opennego.runner import RunRecord, run_experiment_config

DEMO_BUNDLE_SCHEMA_VERSION = "opennego.demo_bundle.v1"
DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION = "opennego.demo_bundle_validation.v1"


@dataclass(frozen=True)
class DemoSummary:
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


@dataclass(frozen=True)
class DemoBundleValidationResult:
    schema_version: str
    status: str
    manifest_file: str
    bundle_schema_version: str | None
    artifacts: Mapping[str, str]
    artifact_schema_versions: Mapping[str, str]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def run_demo(
    *,
    output_dir: str | Path = "runs/demo",
    report_path: str | Path | None = None,
    config_path: str | Path = "configs/real_market_demo.yaml",
    learning_tool_regime: str = "no_tools",
    user_role: str = "buyer",
    opponent_profile_id: str = "seller_hardline_anchor_v1",
) -> DemoSummary:
    """Run benchmark, policy learning, and HTML report generation."""

    bundle_name = "opennegotiation_demo"
    output = Path(output_dir)
    summary = run_experiment_config(config_path, output_dir=output)
    learning_run = _select_learning_run(summary.runs, learning_tool_regime)
    bundle_manifest = output / "demo_manifest.json"
    leaderboard_summary = output / "leaderboard_summary.json"
    battle_report = output / "battle_report.json"
    strategy_candidate = output / "strategy_candidate.json"
    html_report = (
        Path(report_path)
        if report_path is not None
        else output / "opennegotiation_demo.html"
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
        bundle_name=bundle_name,
        schema_version=DEMO_BUNDLE_SCHEMA_VERSION,
    )

    return DemoSummary(
        name=bundle_name,
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


def validate_demo_bundle(manifest_file: str | Path) -> DemoBundleValidationResult:
    """Validate a one-command demo bundle manifest and referenced artifacts."""

    manifest_path = Path(manifest_file)
    errors: list[str] = []
    warnings: list[str] = []
    manifest = _load_manifest_for_validation(manifest_path, errors)
    artifacts = _mapping_value(manifest.get("artifacts") if manifest else None)
    expected_versions = _mapping_value(
        manifest.get("expected_schema_versions") if manifest else None
    )

    if manifest:
        version = manifest.get("schema_version")
        if version != DEMO_BUNDLE_SCHEMA_VERSION:
            errors.append(
                "manifest.schema_version: expected "
                f"{DEMO_BUNDLE_SCHEMA_VERSION!r}, got {version!r}"
            )
        _validate_benchmark_section(manifest, errors)
        _validate_workflow_steps(manifest, errors)
    else:
        version = None

    observed_versions: dict[str, str] = {}
    resolved_artifacts: dict[str, str] = {}
    for key in (
        "leaderboard_summary",
        "battle_report",
        "strategy_candidate",
        "html_report",
    ):
        artifact_value = artifacts.get(key)
        if artifact_value is None:
            errors.append(f"artifacts.{key}: missing")
            continue
        artifact_path = _resolve_bundle_artifact_path(
            manifest_path,
            str(artifact_value),
        )
        resolved_artifacts[key] = str(artifact_path)
        if not artifact_path.exists():
            errors.append(f"artifacts.{key}: missing file {artifact_path}")
            continue
        if key == "html_report":
            if artifact_path.suffix.lower() not in {".html", ".htm"}:
                warnings.append(f"artifacts.{key}: expected HTML file path")
            continue
        observed = _artifact_schema_version(artifact_path)
        observed_versions[key] = observed
        expected = expected_versions.get(key)
        if expected and observed != expected:
            errors.append(
                f"artifacts.{key}.schema_version: expected {expected!r}, got {observed!r}"
            )

    for key in ("leaderboard_summary", "battle_report", "strategy_candidate"):
        if key not in expected_versions:
            errors.append(f"expected_schema_versions.{key}: missing")

    status = "passed" if not errors else "failed"
    return DemoBundleValidationResult(
        schema_version=DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION,
        status=status,
        manifest_file=str(manifest_path),
        bundle_schema_version=str(version) if version is not None else None,
        artifacts=resolved_artifacts,
        artifact_schema_versions=observed_versions,
        errors=tuple(errors),
        warnings=tuple(warnings),
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
    bundle_name: str,
    schema_version: str,
) -> Path:
    manifest = {
        "schema_version": schema_version,
        "name": bundle_name,
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
            "battle_report": BATTLE_REPORT_V2_SCHEMA_VERSION,
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


def _load_manifest_for_validation(
    manifest_path: Path,
    errors: list[str],
) -> Mapping[str, Any]:
    try:
        return read_json(manifest_path)
    except (OSError, ValueError) as exc:
        errors.append(f"manifest: cannot read JSON object from {manifest_path}: {exc}")
        return {}


def _mapping_value(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_benchmark_section(
    manifest: Mapping[str, Any],
    errors: list[str],
) -> None:
    benchmark = manifest.get("benchmark")
    if not isinstance(benchmark, Mapping):
        errors.append("benchmark: expected object")
        return
    completed = benchmark.get("completed")
    failed = benchmark.get("failed")
    if not isinstance(completed, int) or completed < 0:
        errors.append("benchmark.completed: expected non-negative integer")
    if not isinstance(failed, int) or failed < 0:
        errors.append("benchmark.failed: expected non-negative integer")
    if not benchmark.get("learning_run_id"):
        errors.append("benchmark.learning_run_id: missing")
    if not benchmark.get("learning_input_dir"):
        errors.append("benchmark.learning_input_dir: missing")


def _validate_workflow_steps(
    manifest: Mapping[str, Any],
    errors: list[str],
) -> None:
    steps = manifest.get("workflow_steps")
    expected = (
        "benchmark",
        "leaderboard",
        "policy_learning",
        "strategy_evolution",
        "html_report",
    )
    if not isinstance(steps, list):
        errors.append("workflow_steps: expected list")
        return
    observed = tuple(str(step) for step in steps)
    if observed != expected:
        errors.append(
            "workflow_steps: expected "
            f"{', '.join(expected)}, got {', '.join(observed)}"
        )


def _resolve_bundle_artifact_path(
    manifest_path: Path,
    artifact_value: str,
) -> Path:
    artifact_path = Path(artifact_value)
    if artifact_path.exists() or artifact_path.is_absolute():
        return artifact_path
    manifest_dir = manifest_path.parent
    manifest_relative = manifest_dir / artifact_path
    if manifest_relative.exists():
        return manifest_relative
    sibling = manifest_dir / artifact_path.name
    if sibling.exists():
        return sibling
    return artifact_path


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
    raise ValueError("demo bundle requires at least one completed benchmark run")
