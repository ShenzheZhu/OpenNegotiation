"""External no-key handoff package orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from opennego.artifacts import write_json
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH
from opennego.market_validation import validate_market_dataset
from opennego.marketplace import validate_marketplace_configs
from opennego.mvp_demo import run_mvp_demo, validate_mvp_demo_bundle
from opennego.role_swap import run_role_swap_benchmark

EXTERNAL_HANDOFF_SCHEMA_VERSION = "opennego.external_handoff.v1"


@dataclass(frozen=True)
class ExternalHandoffSummary:
    schema_version: str
    status: str
    output_dir: str
    readme: str
    manifest_path: str
    mvp_demo: Mapping[str, Any]
    role_swap: Mapping[str, Any]
    validations: Mapping[str, Any]
    commands: Mapping[str, str]
    boundaries: tuple[str, ...]


def run_external_handoff_package(
    *,
    output_dir: str | Path = "runs/external_handoff",
    config_path: str | Path = "configs/real_market_demo.yaml",
    registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    products_file: str | Path = "examples/data/real_market_products.json",
    market_comps_file: str | Path = "examples/data/real_market_comps.json",
    participant_id: str = "baseline_strategy",
) -> ExternalHandoffSummary:
    """Generate a validated no-key package for external model teams."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    mvp_dir = output / "mvp_demo"
    report_path = output / "reports" / "opennegotiation_mvp_demo.html"
    validations_dir = output / "validations"
    validations_dir.mkdir(parents=True, exist_ok=True)

    mvp_summary = run_mvp_demo(
        output_dir=mvp_dir,
        report_path=report_path,
        config_path=config_path,
    )
    mvp_validation = validate_mvp_demo_bundle(mvp_summary.bundle_manifest)
    mvp_validation_path = validations_dir / "mvp_demo_bundle_validation.json"
    write_json(mvp_validation_path, mvp_validation)

    market_validation = validate_market_dataset(
        products_file=products_file,
        market_comps_file=market_comps_file,
    )
    market_validation_path = validations_dir / "market_validation.json"
    write_json(market_validation_path, market_validation)

    marketplace_validation = validate_marketplace_configs(registry_path=registry_path)
    marketplace_validation_path = validations_dir / "marketplace_validation.json"
    write_json(marketplace_validation_path, marketplace_validation)

    role_swap_summary = run_role_swap_benchmark(
        output_dir=output / "role_swap",
        config_path=config_path,
        participant_id=participant_id,
    )

    status = _handoff_status(
        mvp_benchmark_failed=mvp_summary.benchmark_failed,
        mvp_validation_status=mvp_validation.status,
        market_validation_status=market_validation.status,
        marketplace_validation_status=marketplace_validation.status,
        role_swap_status=role_swap_summary.status,
    )
    readme_path = output / "README.md"
    summary = ExternalHandoffSummary(
        schema_version=EXTERNAL_HANDOFF_SCHEMA_VERSION,
        status=status,
        output_dir=str(output),
        readme=str(readme_path),
        manifest_path=str(output / "handoff_manifest.json"),
        mvp_demo={
            "output_dir": mvp_summary.output_dir,
            "bundle_manifest": mvp_summary.bundle_manifest,
            "leaderboard_summary": mvp_summary.leaderboard_summary,
            "battle_report": mvp_summary.battle_report,
            "strategy_candidate": mvp_summary.strategy_candidate,
            "html_report": mvp_summary.html_report,
            "benchmark_completed": mvp_summary.benchmark_completed,
            "benchmark_failed": mvp_summary.benchmark_failed,
        },
        role_swap={
            "summary": role_swap_summary.artifact_path,
            "leaderboard_summary": role_swap_summary.leaderboard_summary,
            "participant_id": role_swap_summary.participant_id,
            "participant_roles": role_swap_summary.participant_roles,
            "participant_role_coverage": role_swap_summary.participant_role_coverage,
            "completed": role_swap_summary.completed,
            "failed": role_swap_summary.failed,
            "status": role_swap_summary.status,
        },
        validations={
            "mvp_demo_bundle": {
                "path": str(mvp_validation_path),
                "status": mvp_validation.status,
            },
            "market_dataset": {
                "path": str(market_validation_path),
                "status": market_validation.status,
            },
            "strategy_marketplace": {
                "path": str(marketplace_validation_path),
                "status": marketplace_validation.status,
            },
        },
        commands={
            "validate_mvp_bundle": (
                f"opennego validate-demo-bundle --manifest {mvp_summary.bundle_manifest}"
            ),
            "rerun_role_swap": (
                f"opennego role-swap --output-dir {output / 'role_swap'} "
                f"--participant-id {participant_id}"
            ),
            "validate_market": (
                f"opennego validate-market --products-file {products_file} "
                f"--market-comps-file {market_comps_file}"
            ),
            "validate_marketplace": f"opennego validate-marketplace --registry {registry_path}",
        },
        boundaries=(
            "fixture-backed no-key package",
            "no live marketplace collection",
            "no live model-provider calls",
            "no hosted marketplace backend",
        ),
    )
    write_json(summary.manifest_path, summary)
    _write_readme(readme_path, summary)
    return summary


def _handoff_status(
    *,
    mvp_benchmark_failed: int,
    mvp_validation_status: str,
    market_validation_status: str,
    marketplace_validation_status: str,
    role_swap_status: str,
) -> str:
    if (
        mvp_benchmark_failed == 0
        and mvp_validation_status == "passed"
        and market_validation_status == "passed"
        and marketplace_validation_status == "passed"
        and role_swap_status == "completed"
    ):
        return "passed"
    return "failed"


def _write_readme(path: Path, summary: ExternalHandoffSummary) -> None:
    mvp = summary.mvp_demo
    role_swap = summary.role_swap
    validations = summary.validations
    lines = [
        "# OpenNegotiation External Handoff Package",
        "",
        "This package is a no-key, fixture-backed OpenNegotiation handoff for "
        "external model teams. It is intended for local integration smoke tests "
        "and artifact inspection, not as a live marketplace or large-batch benchmark.",
        "",
        f"- Status: `{summary.status}`",
        f"- Handoff manifest: `{Path(summary.manifest_path).name}`",
        f"- MVP bundle manifest: `{_relative(path, mvp['bundle_manifest'])}`",
        f"- MVP HTML report: `{_relative(path, mvp['html_report'])}`",
        f"- MVP leaderboard summary: `{_relative(path, mvp['leaderboard_summary'])}`",
        f"- MVP battle report: `{_relative(path, mvp['battle_report'])}`",
        f"- MVP strategy candidate: `{_relative(path, mvp['strategy_candidate'])}`",
        f"- Role-swap summary: `{_relative(path, role_swap['summary'])}`",
        f"- Role-swap coverage: `{role_swap['participant_role_coverage']}`",
        "",
        "## Validation Results",
        "",
        (
            "- MVP bundle validation: "
            f"`{validations['mvp_demo_bundle']['status']}` "
            f"at `{_relative(path, validations['mvp_demo_bundle']['path'])}`"
        ),
        (
            "- Market dataset validation: "
            f"`{validations['market_dataset']['status']}` "
            f"at `{_relative(path, validations['market_dataset']['path'])}`"
        ),
        (
            "- Strategy marketplace validation: "
            f"`{validations['strategy_marketplace']['status']}` "
            f"at `{_relative(path, validations['strategy_marketplace']['path'])}`"
        ),
        "",
        "## Recheck Commands",
        "",
        "```bash",
        summary.commands["validate_mvp_bundle"],
        summary.commands["rerun_role_swap"],
        summary.commands["validate_market"],
        summary.commands["validate_marketplace"],
        "```",
        "",
        "## Boundaries",
        "",
    ]
    lines.extend(f"- {item}" for item in summary.boundaries)
    path.write_text("\n".join(lines) + "\n")


def _relative(readme_path: Path, value: object) -> str:
    target = Path(str(value))
    try:
        return str(target.relative_to(readme_path.parent))
    except ValueError:
        return str(target)
