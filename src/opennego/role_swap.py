"""No-key role-swapped benchmark track orchestration."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from shutil import copytree
from typing import Any, Mapping

from opennego.artifacts import read_json, write_json
from opennego.leaderboard import build_leaderboard, write_leaderboard
from opennego.runner import ExperimentSummary, run_experiment_config

ROLE_SWAP_SCHEMA_VERSION = "opennego.role_swap_benchmark.v1"


@dataclass(frozen=True)
class RoleSwapBenchmarkSummary:
    schema_version: str
    status: str
    output_dir: str
    config_path: str
    participant_id: str
    buyer_role_config: str
    seller_role_config: str
    buyer_role_output_dir: str
    seller_role_output_dir: str
    combined_runs_dir: str
    leaderboard_summary: str
    completed: int
    failed: int
    participant_roles: tuple[str, ...]
    participant_role_coverage: float
    artifact_path: str


def run_role_swap_benchmark(
    *,
    output_dir: str | Path = "runs/role_swap",
    config_path: str | Path = "configs/real_market_demo.yaml",
    participant_id: str = "baseline_strategy",
) -> RoleSwapBenchmarkSummary:
    """Run the same strategy identity as buyer and seller, then aggregate."""

    if not isinstance(participant_id, str) or not participant_id:
        raise ValueError("participant_id: expected non-empty string")
    output = Path(output_dir)
    config_base = _load_config_mapping(config_path)
    config_dir = output / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    buyer_config_path = config_dir / "buyer_role.json"
    seller_config_path = config_dir / "seller_role.json"
    write_json(
        buyer_config_path,
        _role_config(
            config_base,
            role="buyer",
            output_dir=output / "buyer_role",
            participant_id=participant_id,
        ),
    )
    write_json(
        seller_config_path,
        _role_config(
            config_base,
            role="seller",
            output_dir=output / "seller_role",
            participant_id=participant_id,
        ),
    )

    buyer_summary = run_experiment_config(buyer_config_path)
    seller_summary = run_experiment_config(seller_config_path)
    combined_runs_dir = output / "combined_runs"
    _copy_completed_runs(buyer_summary, combined_runs_dir)
    _copy_completed_runs(seller_summary, combined_runs_dir)
    leaderboard_path = output / "leaderboard_summary.json"
    write_leaderboard(combined_runs_dir, leaderboard_path)
    leaderboard = build_leaderboard(combined_runs_dir)
    participant = _participant_summary(leaderboard, participant_id)
    artifact_path = output / "role_swap_summary.json"
    failed = buyer_summary.failed + seller_summary.failed
    summary = RoleSwapBenchmarkSummary(
        schema_version=ROLE_SWAP_SCHEMA_VERSION,
        status="completed" if failed == 0 else "failed",
        output_dir=str(output),
        config_path=str(config_path),
        participant_id=participant_id,
        buyer_role_config=str(buyer_config_path),
        seller_role_config=str(seller_config_path),
        buyer_role_output_dir=buyer_summary.output_dir,
        seller_role_output_dir=seller_summary.output_dir,
        combined_runs_dir=str(combined_runs_dir),
        leaderboard_summary=str(leaderboard_path),
        completed=buyer_summary.completed + seller_summary.completed,
        failed=failed,
        participant_roles=participant.roles,
        participant_role_coverage=participant.role_coverage,
        artifact_path=str(artifact_path),
    )
    write_json(artifact_path, summary)
    return summary


def _load_config_mapping(config_path: str | Path) -> Mapping[str, Any]:
    data = read_json(config_path)
    if not isinstance(data, Mapping):
        raise ValueError(f"{config_path}: expected experiment config object")
    return data


def _role_config(
    base: Mapping[str, Any],
    *,
    role: str,
    output_dir: Path,
    participant_id: str,
) -> Mapping[str, Any]:
    config = copy.deepcopy(dict(base))
    config["name"] = f"{base.get('name', 'benchmark')}_role_swap_{role}"
    config["output_dir"] = str(output_dir)
    config["resume"] = False
    metadata = dict(config.get("metadata") or {})
    metadata.update(
        {
            "role_swap_track": True,
            "role_swap_participant_id": participant_id,
            "role_swap_user_role": role,
        }
    )
    config["metadata"] = metadata
    config["agents"] = _role_agents(role=role, participant_id=participant_id)
    config["tool_regimes"] = _role_tool_regimes(base, role=role)
    return config


def _role_agents(*, role: str, participant_id: str) -> Mapping[str, Any]:
    if role == "buyer":
        return {
            "buyer": {
                "kind": "tool_aware_buyer",
                "params": {
                    "name": f"{participant_id}:buyer",
                    "participant_id": participant_id,
                },
            },
            "seller": {
                "kind": "scripted_seller",
                "params": {
                    "name": "role_swap_counterparty_seller",
                    "participant_id": "role_swap_counterparty_seller",
                },
            },
        }
    if role == "seller":
        return {
            "buyer": {
                "kind": "tool_aware_buyer",
                "params": {
                    "name": "role_swap_counterparty_buyer",
                    "participant_id": "role_swap_counterparty_buyer",
                },
            },
            "seller": {
                "kind": "scripted_seller",
                "params": {
                    "name": f"{participant_id}:seller",
                    "participant_id": participant_id,
                },
            },
        }
    raise ValueError(f"unsupported role-swap role {role!r}")


def _role_tool_regimes(base: Mapping[str, Any], *, role: str) -> tuple[Mapping[str, Any], ...]:
    source = _market_tool_source(base)
    visibility = "buyer_private" if role == "buyer" else "seller_private"
    return (
        {"id": "no_tools", "tools": []},
        {
            "id": "participant_private_market_search",
            "tools": [
                {
                    "name": "market_price_search",
                    "kind": "market_price",
                    "source": source,
                    "visibility": visibility,
                    "mode": "clean",
                }
            ],
        },
    )


def _market_tool_source(base: Mapping[str, Any]) -> str:
    for regime in base.get("tool_regimes", ()):
        if not isinstance(regime, Mapping):
            continue
        for tool in regime.get("tools", ()):
            if (
                isinstance(tool, Mapping)
                and tool.get("kind") == "market_price"
                and isinstance(tool.get("source"), str)
            ):
                return str(tool["source"])
    return "examples/data/real_market_comps.json"


def _copy_completed_runs(summary: ExperimentSummary, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for record in summary.runs:
        if record.status != "completed":
            continue
        source = Path(record.output_dir)
        target = destination / source.name
        if target.exists():
            raise ValueError(f"{target}: duplicate combined run artifact")
        copytree(source, target)


def _participant_summary(leaderboard, participant_id: str):
    for participant in leaderboard.participant_summaries:
        if participant.participant_id == participant_id:
            return participant
    raise ValueError(f"{participant_id}: missing from role-swapped leaderboard")
