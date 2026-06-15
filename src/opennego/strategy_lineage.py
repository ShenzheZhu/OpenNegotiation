"""Durable strategy evolution lineage.

A strategy config already embeds the lineage of the candidates that built it.
This module records the orthogonal genealogy users iterate through over time:
an append-only chain of applied strategy config versions, each linked to its
parent, the candidate and reports that motivated it, the held-out
generalization verdict, and the accept/reject decision. It is the substrate
for the client's version-history view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from opennego.artifacts import read_json, write_json
from opennego.strategy_config import StrategyConfig

STRATEGY_LINEAGE_SCHEMA_VERSION = "opennego.strategy_lineage.v1"

DECISIONS = ("accepted", "rejected")


class StrategyLineageError(ValueError):
    """Raised when a strategy lineage artifact is malformed or inconsistent."""


@dataclass(frozen=True)
class LineageNode:
    version: int
    parent_version: int | None
    strategy_id: str
    config_path: str
    source_candidate_id: str
    source_battle_report: str
    decision: str
    generalization_verdict: str | None = None
    source_comparison: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise StrategyLineageError(
                f"decision: expected one of {DECISIONS}, got {self.decision!r}"
            )


@dataclass(frozen=True)
class StrategyLineage:
    schema_version: str
    strategy_id: str
    nodes: tuple[LineageNode, ...] = ()

    @property
    def head(self) -> LineageNode | None:
        return self.nodes[-1] if self.nodes else None


def append_strategy_config(
    lineage_path: str | Path,
    config: StrategyConfig,
    config_path: str | Path,
    *,
    decision: str = "accepted",
    source_comparison: str | Path | None = None,
) -> StrategyLineage:
    """Append one applied strategy config to a lineage, creating it if absent.

    The new node's ``parent_version`` is the previous head's version, so the
    chain is self-describing and validatable. The strategy id is fixed by the
    first node; appending a config with a different id is an error.
    """

    path = Path(lineage_path)
    lineage = (
        load_strategy_lineage(path)
        if path.exists()
        else StrategyLineage(
            schema_version=STRATEGY_LINEAGE_SCHEMA_VERSION,
            strategy_id=config.strategy_id,
            nodes=(),
        )
    )
    if lineage.strategy_id != config.strategy_id:
        raise StrategyLineageError(
            f"lineage tracks strategy {lineage.strategy_id!r}, cannot append "
            f"config for {config.strategy_id!r}"
        )
    parent_version = lineage.head.version if lineage.head is not None else None
    verdict = config.metadata.get("generalization_verdict")
    if verdict is None:
        # apply-strategy stamps the verdict onto the candidate, not the config;
        # surface it on the node when the candidate carried one.
        verdict = config.metadata.get("candidate_generalization_verdict")
    node = LineageNode(
        version=config.version,
        parent_version=parent_version,
        strategy_id=config.strategy_id,
        config_path=str(config_path),
        source_candidate_id=config.source_candidate_id,
        source_battle_report=config.source_battle_report,
        decision=decision,
        generalization_verdict=str(verdict) if verdict is not None else None,
        source_comparison=(
            str(source_comparison) if source_comparison is not None else None
        ),
    )
    updated = StrategyLineage(
        schema_version=STRATEGY_LINEAGE_SCHEMA_VERSION,
        strategy_id=lineage.strategy_id,
        nodes=(*lineage.nodes, node),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, updated)
    return updated


def load_strategy_lineage(path: str | Path) -> StrategyLineage:
    lineage_path = Path(path)
    data = read_json(lineage_path)
    version = data.get("schema_version")
    if version != STRATEGY_LINEAGE_SCHEMA_VERSION:
        raise StrategyLineageError(
            f"{lineage_path}: expected {STRATEGY_LINEAGE_SCHEMA_VERSION}, "
            f"got {version!r}"
        )
    strategy_id = data.get("strategy_id")
    if not isinstance(strategy_id, str) or not strategy_id:
        raise StrategyLineageError("strategy_id: expected non-empty string")
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        raise StrategyLineageError("nodes: expected list")
    nodes = tuple(_node_from_mapping(node) for node in raw_nodes)
    return StrategyLineage(
        schema_version=STRATEGY_LINEAGE_SCHEMA_VERSION,
        strategy_id=strategy_id,
        nodes=nodes,
    )


def validate_strategy_lineage(path: str | Path) -> tuple[str, ...]:
    """Return lineage consistency errors: broken links or missing artifacts."""

    lineage_path = Path(path)
    try:
        lineage = load_strategy_lineage(lineage_path)
    except (OSError, StrategyLineageError) as exc:
        return (f"lineage: cannot load: {exc}",)

    errors: list[str] = []
    base_dir = lineage_path.parent
    previous_version: int | None = None
    for index, node in enumerate(lineage.nodes):
        if node.strategy_id != lineage.strategy_id:
            errors.append(
                f"nodes[{index}].strategy_id: {node.strategy_id!r} does not "
                f"match lineage {lineage.strategy_id!r}"
            )
        if index == 0:
            if node.parent_version is not None:
                errors.append("nodes[0].parent_version: first node must have no parent")
        elif node.parent_version != previous_version:
            errors.append(
                f"nodes[{index}].parent_version: expected {previous_version!r}, "
                f"got {node.parent_version!r}"
            )
        if not _artifact_exists(base_dir, node.config_path):
            errors.append(
                f"nodes[{index}].config_path: missing artifact {node.config_path}"
            )
        previous_version = node.version
    return tuple(errors)


def _artifact_exists(base_dir: Path, artifact_path: str) -> bool:
    candidate = Path(artifact_path)
    if candidate.exists():
        return True
    return (base_dir / candidate.name).exists()


def _node_from_mapping(data: Any) -> LineageNode:
    if not isinstance(data, Mapping):
        raise StrategyLineageError("nodes[]: expected object")
    version = data.get("version")
    if not isinstance(version, int):
        raise StrategyLineageError("nodes[].version: expected integer")
    parent_version = data.get("parent_version")
    if parent_version is not None and not isinstance(parent_version, int):
        raise StrategyLineageError("nodes[].parent_version: expected integer or null")
    return LineageNode(
        version=version,
        parent_version=parent_version,
        strategy_id=str(data.get("strategy_id", "")),
        config_path=str(data.get("config_path", "")),
        source_candidate_id=str(data.get("source_candidate_id", "")),
        source_battle_report=str(data.get("source_battle_report", "")),
        decision=str(data.get("decision", "accepted")),
        generalization_verdict=(
            str(data["generalization_verdict"])
            if data.get("generalization_verdict") is not None
            else None
        ),
        source_comparison=(
            str(data["source_comparison"])
            if data.get("source_comparison") is not None
            else None
        ),
    )
