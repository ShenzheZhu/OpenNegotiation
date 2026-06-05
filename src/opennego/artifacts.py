"""Versioned benchmark artifact contracts and JSON I/O helpers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.metrics import compute_metrics
from opennego.schema import (
    ActionType,
    Offer,
    Product,
    Role,
    RunResult,
    Scenario,
    ToolCall,
    TransactionOutcome,
    TranscriptEvent,
)

ARTIFACT_SCHEMA_VERSION = "opennego.benchmark.v1"


class ArtifactValidationError(ValueError):
    """Raised when a benchmark artifact does not satisfy the current contract."""


@dataclass(frozen=True)
class ScenarioArtifact:
    schema_version: str
    scenario_id: str
    product: Product
    buyer_budget: float
    seller_reservation_price: float
    max_turns: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_scenario(
        cls,
        scenario: Scenario,
        scenario_id: str | None = None,
    ) -> "ScenarioArtifact":
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            scenario_id=scenario_id or scenario.product.id,
            product=scenario.product,
            buyer_budget=scenario.buyer_budget,
            seller_reservation_price=scenario.seller_reservation_price,
            max_turns=scenario.max_turns,
            metadata=scenario.metadata,
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ScenarioArtifact":
        _require_version(data)
        scenario_id = _required_str(data, "scenario_id")
        product_data = _required_mapping(data, "product")
        try:
            product = Product.from_mapping(product_data)
        except (TypeError, ValueError) as exc:
            raise ArtifactValidationError(f"product: {exc}") from exc
        buyer_budget = _required_number(data, "buyer_budget")
        seller_reservation_price = _required_number(data, "seller_reservation_price")
        max_turns = int(_required_number(data, "max_turns"))
        if buyer_budget <= 0:
            raise ArtifactValidationError("buyer_budget: expected positive number")
        if seller_reservation_price <= 0:
            raise ArtifactValidationError("seller_reservation_price: expected positive number")
        if max_turns <= 0:
            raise ArtifactValidationError("max_turns: expected positive integer")
        metadata = _optional_mapping(data, "metadata")
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            scenario_id=scenario_id,
            product=product,
            buyer_budget=buyer_budget,
            seller_reservation_price=seller_reservation_price,
            max_turns=max_turns,
            metadata=metadata,
        )

    def to_scenario(self) -> Scenario:
        return Scenario(
            product=self.product,
            buyer_budget=self.buyer_budget,
            seller_reservation_price=self.seller_reservation_price,
            max_turns=self.max_turns,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class RunManifest:
    schema_version: str
    run_id: str
    scenario_id: str
    seed: int | None
    agents: Mapping[str, Any]
    models: Mapping[str, Any] = field(default_factory=dict)
    tool_regime: Mapping[str, Any] = field(default_factory=dict)
    output_paths: Mapping[str, str] = field(default_factory=dict)
    code_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        scenario_id: str,
        seed: int | None,
        agents: Mapping[str, Any],
        models: Mapping[str, Any] | None = None,
        tool_regime: Mapping[str, Any] | None = None,
        output_paths: Mapping[str, str] | None = None,
        code_metadata: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "RunManifest":
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            run_id=run_id,
            scenario_id=scenario_id,
            seed=seed,
            agents=dict(agents),
            models=dict(models or {}),
            tool_regime=dict(tool_regime or {}),
            output_paths=dict(output_paths or {}),
            code_metadata=dict(code_metadata or {}),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RunManifest":
        _require_version(data)
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            run_id=_required_str(data, "run_id"),
            scenario_id=_required_str(data, "scenario_id"),
            seed=_optional_int(data, "seed"),
            agents=_required_mapping(data, "agents"),
            models=_optional_mapping(data, "models"),
            tool_regime=_optional_mapping(data, "tool_regime"),
            output_paths=_optional_str_mapping(data, "output_paths"),
            code_metadata=_optional_mapping(data, "code_metadata"),
            metadata=_optional_mapping(data, "metadata"),
        )


@dataclass(frozen=True)
class TraceEventRecord:
    schema_version: str
    run_id: str
    scenario_id: str
    event_index: int
    turn: int
    role: Role
    actor: str
    action_type: ActionType
    private: bool
    content: str = ""
    offer: Offer | None = None
    tool_call: ToolCall | None = None
    tool_result: Mapping[str, Any] | None = None
    transaction: TransactionOutcome | None = None
    error: Mapping[str, Any] | None = None

    @classmethod
    def from_event(
        cls,
        *,
        run_id: str,
        scenario_id: str,
        event_index: int,
        event: TranscriptEvent,
    ) -> "TraceEventRecord":
        error = None
        if event.tool_result and event.tool_result.get("ok") is False:
            error = {
                "source": "tool",
                "message": str(event.tool_result.get("error", "tool call failed")),
            }
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            run_id=run_id,
            scenario_id=scenario_id,
            event_index=event_index,
            turn=event.turn,
            role=event.role,
            actor=event.actor,
            action_type=event.action_type,
            private=event.private,
            content=event.content,
            offer=event.offer,
            tool_call=event.tool_call,
            tool_result=event.tool_result,
            transaction=event.transaction,
            error=error,
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TraceEventRecord":
        _require_version(data)
        offer_data = data.get("offer")
        tool_call_data = data.get("tool_call")
        transaction_data = data.get("transaction")
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            run_id=_required_str(data, "run_id"),
            scenario_id=_required_str(data, "scenario_id"),
            event_index=int(_required_number(data, "event_index")),
            turn=int(_required_number(data, "turn")),
            role=Role(_required_str(data, "role")),
            actor=_required_str(data, "actor"),
            action_type=ActionType(_required_str(data, "action_type")),
            private=bool(data.get("private", False)),
            content=str(data.get("content", "")),
            offer=_offer_from_mapping(offer_data) if offer_data else None,
            tool_call=_tool_call_from_mapping(tool_call_data) if tool_call_data else None,
            tool_result=data.get("tool_result"),
            transaction=_transaction_from_mapping(transaction_data) if transaction_data else None,
            error=data.get("error"),
        )

    def to_transcript_event(self) -> TranscriptEvent:
        return TranscriptEvent(
            turn=self.turn,
            role=self.role,
            actor=self.actor,
            action_type=self.action_type,
            content=self.content,
            offer=self.offer,
            tool_call=self.tool_call,
            tool_result=self.tool_result,
            transaction=self.transaction,
            private=self.private,
        )


@dataclass(frozen=True)
class MetricReport:
    schema_version: str
    run_id: str
    scenario_id: str
    outcome: str
    deal_price: float | None
    completed_turns: int
    metrics: Mapping[str, float]

    @classmethod
    def from_result(
        cls,
        *,
        run_id: str,
        scenario_id: str,
        result: RunResult,
    ) -> "MetricReport":
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            run_id=run_id,
            scenario_id=scenario_id,
            outcome=result.outcome,
            deal_price=result.deal_price,
            completed_turns=result.completed_turns,
            metrics=dict(result.metrics),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MetricReport":
        _require_version(data)
        deal_price = data.get("deal_price")
        return cls(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            run_id=_required_str(data, "run_id"),
            scenario_id=_required_str(data, "scenario_id"),
            outcome=_required_str(data, "outcome"),
            deal_price=float(deal_price) if deal_price is not None else None,
            completed_turns=int(_required_number(data, "completed_turns")),
            metrics={
                key: float(value)
                for key, value in _required_mapping(data, "metrics").items()
            },
        )


@dataclass(frozen=True)
class ArtifactPaths:
    output_dir: Path
    manifest_path: Path
    scenario_path: Path
    trace_path: Path
    metrics_path: Path


def write_run_artifacts(
    *,
    result: RunResult,
    output_dir: str | Path,
    run_id: str,
    scenario_id: str | None = None,
    seed: int | None = None,
    agents: Mapping[str, Any] | None = None,
    models: Mapping[str, Any] | None = None,
    tool_regime: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactPaths:
    scenario_artifact = ScenarioArtifact.from_scenario(result.scenario, scenario_id=scenario_id)
    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = ArtifactPaths(
        output_dir=base_dir,
        manifest_path=base_dir / "manifest.json",
        scenario_path=base_dir / "scenario.json",
        trace_path=base_dir / "trace.jsonl",
        metrics_path=base_dir / "metrics.json",
    )
    manifest = RunManifest.create(
        run_id=run_id,
        scenario_id=scenario_artifact.scenario_id,
        seed=seed,
        agents=agents or {},
        models=models,
        tool_regime=tool_regime,
        output_paths={
            "manifest": paths.manifest_path.name,
            "scenario": paths.scenario_path.name,
            "trace": paths.trace_path.name,
            "metrics": paths.metrics_path.name,
        },
        code_metadata=collect_code_metadata(),
        metadata=metadata,
    )
    trace_records = [
        TraceEventRecord.from_event(
            run_id=run_id,
            scenario_id=scenario_artifact.scenario_id,
            event_index=index,
            event=event,
        )
        for index, event in enumerate(result.events)
    ]
    metric_report = MetricReport.from_result(
        run_id=run_id,
        scenario_id=scenario_artifact.scenario_id,
        result=result,
    )

    write_json(paths.scenario_path, scenario_artifact)
    write_json(paths.manifest_path, manifest)
    write_jsonl(paths.trace_path, trace_records)
    write_json(paths.metrics_path, metric_report)
    return paths


def load_scenario_artifact(path: str | Path) -> ScenarioArtifact:
    return ScenarioArtifact.from_mapping(read_json(path))


def load_manifest(path: str | Path) -> RunManifest:
    return RunManifest.from_mapping(read_json(path))


def load_trace(path: str | Path) -> list[TraceEventRecord]:
    return [TraceEventRecord.from_mapping(record) for record in read_jsonl(path)]


def load_metric_report(path: str | Path) -> MetricReport:
    return MetricReport.from_mapping(read_json(path))


def recompute_metrics_from_artifacts(
    scenario_artifact: ScenarioArtifact,
    trace_records: Sequence[TraceEventRecord],
) -> Mapping[str, float]:
    events = [record.to_transcript_event() for record in trace_records]
    deal_price = _deal_price_from_trace(trace_records)
    outcome = "deal" if deal_price is not None else "timeout"
    return compute_metrics(scenario_artifact.to_scenario(), outcome, deal_price, events)


def collect_code_metadata() -> Mapping[str, Any]:
    return {
        "git_commit": _git(["rev-parse", "HEAD"]),
        "git_branch": _git(["branch", "--show-current"]),
    }


def write_json(path: str | Path, value: Any) -> None:
    Path(path).write_text(json.dumps(to_jsonable(value), indent=2, sort_keys=True) + "\n")


def read_json(path: str | Path) -> Mapping[str, Any]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, Mapping):
        raise ArtifactValidationError(f"{path}: expected JSON object")
    return data


def write_jsonl(path: str | Path, values: Sequence[Any]) -> None:
    lines = [json.dumps(to_jsonable(value), sort_keys=True) for value in values]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""))


def read_jsonl(path: str | Path) -> list[Mapping[str, Any]]:
    records = []
    for line_number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, Mapping):
            raise ArtifactValidationError(f"{path}:{line_number}: expected JSON object")
        records.append(record)
    return records


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def _require_version(data: Mapping[str, Any]) -> None:
    version = data.get("schema_version")
    if version != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactValidationError(
            f"schema_version: expected {ARTIFACT_SCHEMA_VERSION!r}, got {version!r}"
        )


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError(f"{key}: expected non-empty string")
    return value


def _required_number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)):
        raise ArtifactValidationError(f"{key}: expected number")
    return float(value)


def _required_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ArtifactValidationError(f"{key}: expected object")
    return value


def _optional_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ArtifactValidationError(f"{key}: expected object")
    return value


def _optional_str_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, str]:
    mapping = _optional_mapping(data, key)
    return {str(item_key): str(item_value) for item_key, item_value in mapping.items()}


def _optional_int(data: Mapping[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ArtifactValidationError(f"{key}: expected integer or null")
    return value


def _offer_from_mapping(data: Any) -> Offer:
    if not isinstance(data, Mapping):
        raise ArtifactValidationError("offer: expected object")
    return Offer(
        price=_required_number(data, "price"),
        note=str(data.get("note", "")),
        metadata=_optional_mapping(data, "metadata"),
    )


def _tool_call_from_mapping(data: Any) -> ToolCall:
    if not isinstance(data, Mapping):
        raise ArtifactValidationError("tool_call: expected object")
    return ToolCall(
        name=_required_str(data, "name"),
        arguments=_optional_mapping(data, "arguments"),
    )


def _transaction_from_mapping(data: Any) -> TransactionOutcome:
    if not isinstance(data, Mapping):
        raise ArtifactValidationError("transaction: expected object")
    return TransactionOutcome(
        status=_required_str(data, "status"),
        negotiated_price=_required_number(data, "negotiated_price"),
        buyer_total_cost=_required_number(data, "buyer_total_cost"),
        seller_net_revenue=_required_number(data, "seller_net_revenue"),
        shipping_cost=_optional_number(data, "shipping_cost"),
        tax=_optional_number(data, "tax"),
        escrow_fee=_optional_number(data, "escrow_fee"),
        payment_fee=_optional_number(data, "payment_fee"),
        seller_fee=_optional_number(data, "seller_fee"),
        return_risk=_optional_number(data, "return_risk"),
        reputation_risk=_optional_number(data, "reputation_risk"),
        risk_exposure=_optional_number(data, "risk_exposure"),
        failure_reason=data.get("failure_reason"),
        metadata=_optional_mapping(data, "metadata"),
    )


def _deal_price_from_trace(trace_records: Sequence[TraceEventRecord]) -> float | None:
    latest_offer: Offer | None = None
    latest_offer_role: Role | None = None
    for record in trace_records:
        if record.action_type == ActionType.OFFER and record.offer is not None:
            latest_offer = record.offer
            latest_offer_role = record.role
        if (
            record.action_type == ActionType.ACCEPT
            and latest_offer is not None
            and latest_offer_role != record.role
        ):
            return latest_offer.price
    return None


def _optional_number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key, 0.0)
    if not isinstance(value, (int, float)):
        raise ArtifactValidationError(f"{key}: expected number")
    return float(value)


def _git(args: Sequence[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None
