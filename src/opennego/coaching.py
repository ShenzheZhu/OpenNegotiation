"""Coach case construction and the battle report v2 schema.

See ``docs/design/coach.md``. The case builder enforces the visibility red
line: a coach sees exactly what the user agent could have seen during the
run, plus the opponent's public registry card. Counterpart private
constraints, the counterpart side of the BATNA derivation, counterpart
private tool traffic, and NPC policy internals never enter a case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import (
    MetricReport,
    TraceEventRecord,
    load_manifest,
    load_metric_report,
    load_scenario_artifact,
    load_trace,
)
from opennego.learning import StrategyProfile, load_strategy_registry
from opennego.schema import Role

BATTLE_REPORT_V2_SCHEMA_VERSION = "opennego.battle_report.v2"

PHASES = ("selection", "negotiation", "closing", "safety")
SEVERITIES = ("minor", "major", "critical")

# Derived metrics that let one side reconstruct the counterpart's private
# constraint from the deal price. They are stripped from the case by role:
# slack reveals the buyer's budget; profit-vs-reservation reveals the seller's
# floor; normalized_deal_price is anchored on the seller-side cost basis.
COUNTERPART_PRIVATE_METRICS: Mapping[Role, tuple[str, ...]] = {
    Role.BUYER: ("seller_profit_vs_reservation", "normalized_deal_price"),
    Role.SELLER: ("buyer_budget_slack",),
}


class BattleReportValidationError(ValueError):
    """Raised when a battle report violates the v2 contract."""


@dataclass(frozen=True)
class OutcomeSummary:
    outcome: str
    deal_price: float | None = None
    surplus_assessment: str = ""


@dataclass(frozen=True)
class OpponentRead:
    observed_tactics: tuple[str, ...] = ()
    archetype_guess: str | None = None
    confidence: str = "low"


@dataclass(frozen=True)
class DecisionPoint:
    turn: int
    phase: str
    situation: str
    action_taken: str
    assessment: str
    counterfactual: str = ""

    def __post_init__(self) -> None:
        _require_phase(self.phase, "decision_points")


@dataclass(frozen=True)
class Weakness:
    id: str
    phase: str
    severity: str
    summary: str
    evidence_turns: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _require_phase(self.phase, "weaknesses")
        if self.severity not in SEVERITIES:
            raise BattleReportValidationError(
                f"weaknesses.severity: expected one of {SEVERITIES}, "
                f"got {self.severity!r}"
            )


@dataclass(frozen=True)
class Lesson:
    id: str
    patch: str


@dataclass(frozen=True)
class SafetyVerdict:
    passed: bool = True
    violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class BattleReport:
    schema_version: str
    run_id: str
    user_role: Role
    coach: Mapping[str, Any]
    outcome_summary: OutcomeSummary
    opponent_read: OpponentRead = OpponentRead()
    decision_points: tuple[DecisionPoint, ...] = ()
    weaknesses: tuple[Weakness, ...] = ()
    lessons: tuple[Lesson, ...] = ()
    safety: SafetyVerdict = SafetyVerdict()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BattleReport":
        version = data.get("schema_version")
        if version != BATTLE_REPORT_V2_SCHEMA_VERSION:
            raise BattleReportValidationError(
                "schema_version: expected "
                f"{BATTLE_REPORT_V2_SCHEMA_VERSION!r}, got {version!r}"
            )
        outcome = data.get("outcome_summary")
        if not isinstance(outcome, Mapping) or "outcome" not in outcome:
            raise BattleReportValidationError(
                "outcome_summary: expected object with outcome"
            )
        read = data.get("opponent_read") or {}
        safety = data.get("safety") or {}
        return cls(
            schema_version=BATTLE_REPORT_V2_SCHEMA_VERSION,
            run_id=str(data.get("run_id", "")),
            user_role=Role(str(data["user_role"])),
            coach=dict(data.get("coach", {})),
            outcome_summary=OutcomeSummary(
                outcome=str(outcome["outcome"]),
                deal_price=(
                    float(outcome["deal_price"])
                    if outcome.get("deal_price") is not None
                    else None
                ),
                surplus_assessment=str(outcome.get("surplus_assessment", "")),
            ),
            opponent_read=OpponentRead(
                observed_tactics=tuple(
                    str(item) for item in read.get("observed_tactics", ())
                ),
                archetype_guess=(
                    str(read["archetype_guess"])
                    if read.get("archetype_guess") is not None
                    else None
                ),
                confidence=str(read.get("confidence", "low")),
            ),
            decision_points=tuple(
                DecisionPoint(
                    turn=int(point["turn"]),
                    phase=str(point["phase"]),
                    situation=str(point.get("situation", "")),
                    action_taken=str(point.get("action_taken", "")),
                    assessment=str(point.get("assessment", "")),
                    counterfactual=str(point.get("counterfactual", "")),
                )
                for point in data.get("decision_points", ())
            ),
            weaknesses=tuple(
                Weakness(
                    id=str(item["id"]),
                    phase=str(item["phase"]),
                    severity=str(item["severity"]),
                    summary=str(item.get("summary", "")),
                    evidence_turns=tuple(
                        int(turn) for turn in item.get("evidence_turns", ())
                    ),
                )
                for item in data.get("weaknesses", ())
            ),
            lessons=tuple(
                Lesson(id=str(item["id"]), patch=str(item.get("patch", "")))
                for item in data.get("lessons", ())
            ),
            safety=SafetyVerdict(
                passed=bool(safety.get("passed", True)),
                violations=tuple(
                    str(item) for item in safety.get("violations", ())
                ),
            ),
        )


@dataclass(frozen=True)
class CoachCase:
    """The filtered, user-visible view of one completed run."""

    run_id: str
    user_role: Role
    scenario_public: Mapping[str, Any]
    user_private: Mapping[str, Any]
    visible_trace: tuple[TraceEventRecord, ...]
    metrics: MetricReport
    rules: Mapping[str, Any] | None = None
    opponent_card: Mapping[str, Any] | None = None

    @property
    def visible_turns(self) -> tuple[int, ...]:
        return tuple(event.turn for event in self.visible_trace)


def build_coach_case(
    run_dir: str | Path,
    *,
    user_role: Role | str,
    registry_path: str | Path | None = None,
    opponent_profile_id: str | None = None,
) -> CoachCase:
    """Load one run's artifacts and filter them to the user-visible view."""

    role = Role(user_role)
    output_dir = Path(run_dir)
    manifest = load_manifest(output_dir / "manifest.json")
    scenario = load_scenario_artifact(output_dir / "scenario.json")
    metrics = load_metric_report(output_dir / "metrics.json")
    trace = load_trace(output_dir / "trace.jsonl")

    visible_trace = tuple(
        event for event in trace if not event.private or event.role == role
    )
    manifest_metadata = (
        manifest.metadata if isinstance(manifest.metadata, Mapping) else {}
    )
    rules = manifest_metadata.get("rules")
    if not isinstance(rules, Mapping) or not rules.get("enabled"):
        rules = None

    return CoachCase(
        run_id=manifest.run_id,
        user_role=role,
        scenario_public=_scenario_public(scenario),
        user_private=_user_private(scenario, role),
        visible_trace=visible_trace,
        metrics=_role_filtered_metrics(metrics, role),
        rules=dict(rules) if rules is not None else None,
        opponent_card=_opponent_card(
            manifest_metadata=manifest_metadata,
            registry_path=registry_path,
            opponent_profile_id=opponent_profile_id,
        ),
    )


def validate_battle_report(
    report: BattleReport,
    *,
    case: CoachCase | None = None,
) -> tuple[str, ...]:
    """Check a report against the v2 contract and, optionally, grounding.

    With a case, every decision-point turn and weakness evidence turn must
    reference a turn the user could actually see; ungrounded analysis is an
    error, not a style problem.
    """

    errors: list[str] = []
    if case is not None:
        visible = set(case.visible_turns)
        if report.run_id != case.run_id:
            errors.append(
                f"run_id: report {report.run_id!r} does not match case "
                f"{case.run_id!r}"
            )
        if report.user_role != case.user_role:
            errors.append("user_role: report does not match case")
        for point in report.decision_points:
            if point.turn not in visible:
                errors.append(
                    f"decision_points.turn: {point.turn} is not a visible turn"
                )
        for weakness in report.weaknesses:
            for turn in weakness.evidence_turns:
                if turn not in visible:
                    errors.append(
                        f"weaknesses[{weakness.id}].evidence_turns: "
                        f"{turn} is not a visible turn"
                    )
    if not report.safety.passed and not report.safety.violations:
        errors.append("safety: failed verdict requires at least one violation")
    return tuple(errors)


OPPONENT_CARD_FIELDS = (
    "id",
    "name",
    "archetype",
    "difficulty",
    "summary",
    "expected_traps",
    "tags",
)


def public_opponent_card(profile: StrategyProfile) -> Mapping[str, Any]:
    """Expose only the registry card a real counterpart would advertise."""

    return {
        "id": profile.id,
        "name": profile.name,
        "archetype": profile.archetype,
        "difficulty": profile.difficulty,
        "summary": profile.summary,
        "expected_traps": list(profile.expected_traps),
        "tags": list(profile.tags),
    }


def _scenario_public(scenario: Any) -> Mapping[str, Any]:
    metadata = {
        key: value
        for key, value in dict(scenario.metadata or {}).items()
        if key != "batna"
    }
    product = scenario.product
    return {
        "scenario_id": scenario.scenario_id,
        "product": {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "condition": product.condition,
            "list_price": product.list_price,
            "market_reference": (
                {
                    "reference_price": product.market_reference.reference_price,
                    "p25_price": product.market_reference.p25_price,
                    "p75_price": product.market_reference.p75_price,
                    "sample_size": product.market_reference.sample_size,
                    "window_days": product.market_reference.window_days,
                    "source": product.market_reference.source,
                }
                if product.market_reference is not None
                else None
            ),
        },
        "max_turns": scenario.max_turns,
        "metadata": metadata,
    }


def _user_private(scenario: Any, role: Role) -> Mapping[str, Any]:
    metadata = scenario.metadata or {}
    batna = metadata.get("batna") if isinstance(metadata, Mapping) else None
    side_key = "buyer" if role == Role.BUYER else "seller"
    private: dict[str, Any] = {}
    if role == Role.BUYER:
        private["budget"] = scenario.buyer_budget
    else:
        private["reservation_price"] = scenario.seller_reservation_price
    if isinstance(batna, Mapping) and isinstance(batna.get(side_key), Mapping):
        private["outside_option"] = dict(batna[side_key])
    return private


def _role_filtered_metrics(metrics: MetricReport, role: Role) -> MetricReport:
    excluded = set(COUNTERPART_PRIVATE_METRICS.get(role, ()))
    return MetricReport(
        schema_version=metrics.schema_version,
        run_id=metrics.run_id,
        scenario_id=metrics.scenario_id,
        outcome=metrics.outcome,
        deal_price=metrics.deal_price,
        completed_turns=metrics.completed_turns,
        metrics={
            key: value
            for key, value in metrics.metrics.items()
            if key not in excluded
        },
    )


def _opponent_card(
    *,
    manifest_metadata: Mapping[str, Any],
    registry_path: str | Path | None,
    opponent_profile_id: str | None,
) -> Mapping[str, Any] | None:
    profile_id = opponent_profile_id
    if profile_id is None:
        candidate = manifest_metadata.get("opponent_profile_id") or (
            manifest_metadata.get("npc_profile_id")
        )
        if isinstance(candidate, str) and candidate:
            profile_id = candidate
    if profile_id is None:
        return None
    registry = (
        load_strategy_registry(registry_path)
        if registry_path is not None
        else load_strategy_registry()
    )
    try:
        profile = registry.by_id(profile_id)
    except KeyError:
        return None
    return public_opponent_card(profile)


def _require_phase(phase: str, context: str) -> None:
    if phase not in PHASES:
        raise BattleReportValidationError(
            f"{context}.phase: expected one of {PHASES}, got {phase!r}"
        )
