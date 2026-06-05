"""Policy-learning reports and NPC strategy registry utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import (
    MetricReport,
    RunManifest,
    ScenarioArtifact,
    TraceEventRecord,
    load_manifest,
    load_metric_report,
    load_scenario_artifact,
    load_trace,
    to_jsonable,
    write_json,
)
from opennego.branding import PRODUCT_NAME
from opennego.schema import ActionType, Role

POLICY_LEARNING_SCHEMA_VERSION = "opennego.policy_learning.v1"
DEFAULT_NPC_REGISTRY_PATH = Path("examples/data/npc_strategies.json")


@dataclass(frozen=True)
class StrategyProfile:
    """A preset NPC or strategy module that users can spar against."""

    id: str
    name: str
    role: Role
    archetype: str
    difficulty: str
    summary: str
    base_prompt: str
    strategy_prompt: str
    expected_traps: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "StrategyProfile":
        return cls(
            id=_required_str(data, "id"),
            name=_required_str(data, "name"),
            role=Role(_required_str(data, "role")),
            archetype=_required_str(data, "archetype"),
            difficulty=_required_str(data, "difficulty"),
            summary=str(data.get("summary", "")),
            base_prompt=_required_str(data, "base_prompt"),
            strategy_prompt=_required_str(data, "strategy_prompt"),
            expected_traps=tuple(str(item) for item in data.get("expected_traps", ())),
            allowed_tools=tuple(str(item) for item in data.get("allowed_tools", ())),
            tags=tuple(str(item) for item in data.get("tags", ())),
            metadata=_optional_mapping(data, "metadata"),
        )


@dataclass(frozen=True)
class StrategyRegistry:
    schema_version: str
    profiles: tuple[StrategyProfile, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "StrategyRegistry":
        version = data.get("schema_version")
        if version != POLICY_LEARNING_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version: expected {POLICY_LEARNING_SCHEMA_VERSION!r}, got {version!r}"
            )
        profiles = data.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            raise ValueError("profiles: expected non-empty list")
        parsed = tuple(
            StrategyProfile.from_mapping(profile)
            for profile in profiles
            if isinstance(profile, Mapping)
        )
        if len(parsed) != len(profiles):
            raise ValueError("profiles: every item must be an object")
        ids = [profile.id for profile in parsed]
        if len(ids) != len(set(ids)):
            raise ValueError("profiles: ids must be unique")
        return cls(schema_version=POLICY_LEARNING_SCHEMA_VERSION, profiles=parsed)

    @classmethod
    def from_json(cls, path: str | Path) -> "StrategyRegistry":
        data = json.loads(Path(path).read_text())
        if not isinstance(data, Mapping):
            raise ValueError(f"{path}: expected JSON object")
        return cls.from_mapping(data)

    def by_id(self, profile_id: str) -> StrategyProfile:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        raise KeyError(f"Unknown strategy profile: {profile_id}")

    def for_role(self, role: Role | str) -> tuple[StrategyProfile, ...]:
        normalized = Role(role)
        return tuple(profile for profile in self.profiles if profile.role == normalized)


@dataclass(frozen=True)
class EvidenceRef:
    event_index: int
    turn: int
    role: Role
    action_type: ActionType
    summary: str


@dataclass(frozen=True)
class PolicyLesson:
    id: str
    severity: str
    category: str
    finding: str
    recommendation: str
    evidence: tuple[EvidenceRef, ...] = ()
    suggested_strategy_patch: str | None = None


@dataclass(frozen=True)
class BattleReport:
    schema_version: str
    run_id: str
    scenario_id: str
    user_role: Role
    opponent_profile_id: str | None
    outcome: str
    deal_price: float | None
    score: float
    summary: str
    failure_modes: tuple[str, ...]
    strengths: tuple[str, ...]
    lessons: tuple[PolicyLesson, ...]
    suggested_strategy_prompt: str
    artifacts: Mapping[str, str]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedRun:
    output_dir: Path
    manifest: RunManifest
    scenario: ScenarioArtifact
    metrics: MetricReport
    trace: tuple[TraceEventRecord, ...]


def load_strategy_registry(path: str | Path = DEFAULT_NPC_REGISTRY_PATH) -> StrategyRegistry:
    return StrategyRegistry.from_json(path)


def generate_battle_report(
    run_dir: str | Path,
    *,
    user_role: Role | str = Role.BUYER,
    npc_registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    opponent_profile_id: str | None = None,
) -> BattleReport:
    run = _load_run(run_dir)
    registry = load_strategy_registry(npc_registry_path)
    role = Role(user_role)
    opponent_profile = _resolve_opponent_profile(
        registry=registry,
        role=role,
        explicit_profile_id=opponent_profile_id,
        manifest=run.manifest,
    )
    lessons = tuple(_derive_lessons(run, role, opponent_profile))
    strengths = tuple(_derive_strengths(run, role))
    failure_modes = tuple(sorted({lesson.category for lesson in lessons if lesson.severity in {"high", "medium"}}))
    score = _policy_score(run, lessons)
    summary = _summary(run, role, opponent_profile, score, lessons)
    return BattleReport(
        schema_version=POLICY_LEARNING_SCHEMA_VERSION,
        run_id=run.manifest.run_id,
        scenario_id=run.scenario.scenario_id,
        user_role=role,
        opponent_profile_id=opponent_profile.id if opponent_profile else None,
        outcome=run.metrics.outcome,
        deal_price=run.metrics.deal_price,
        score=score,
        summary=summary,
        failure_modes=failure_modes,
        strengths=strengths,
        lessons=lessons,
        suggested_strategy_prompt=_suggested_strategy_prompt(role, lessons),
        artifacts={
            "manifest": str(run.output_dir / "manifest.json"),
            "scenario": str(run.output_dir / "scenario.json"),
            "trace": str(run.output_dir / "trace.jsonl"),
            "metrics": str(run.output_dir / "metrics.json"),
        },
        metadata={
            "opponent_archetype": opponent_profile.archetype if opponent_profile else None,
            "opponent_difficulty": opponent_profile.difficulty if opponent_profile else None,
            "base_prompt_fixed": True,
            "strategy_prompt_editable": True,
        },
    )


def write_battle_report(
    run_dir: str | Path,
    output_path: str | Path,
    *,
    user_role: Role | str = Role.BUYER,
    npc_registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    opponent_profile_id: str | None = None,
) -> Path:
    report = generate_battle_report(
        run_dir,
        user_role=user_role,
        npc_registry_path=npc_registry_path,
        opponent_profile_id=opponent_profile_id,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, report)
    return path


def registry_listing(
    registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    *,
    role: Role | str | None = None,
) -> Mapping[str, Any]:
    registry = load_strategy_registry(registry_path)
    profiles = registry.profiles if role is None else registry.for_role(Role(role))
    return {
        "schema_version": registry.schema_version,
        "profiles": [
            {
                "id": profile.id,
                "name": profile.name,
                "role": profile.role.value,
                "archetype": profile.archetype,
                "difficulty": profile.difficulty,
                "summary": profile.summary,
                "expected_traps": list(profile.expected_traps),
                "allowed_tools": list(profile.allowed_tools),
                "tags": list(profile.tags),
            }
            for profile in profiles
        ],
    }


def _load_run(run_dir: str | Path) -> LoadedRun:
    output_dir = Path(run_dir)
    return LoadedRun(
        output_dir=output_dir,
        manifest=load_manifest(output_dir / "manifest.json"),
        scenario=load_scenario_artifact(output_dir / "scenario.json"),
        metrics=load_metric_report(output_dir / "metrics.json"),
        trace=tuple(load_trace(output_dir / "trace.jsonl")),
    )


def _resolve_opponent_profile(
    *,
    registry: StrategyRegistry,
    role: Role,
    explicit_profile_id: str | None,
    manifest: RunManifest,
) -> StrategyProfile | None:
    if explicit_profile_id:
        return registry.by_id(explicit_profile_id)
    metadata = manifest.metadata if isinstance(manifest.metadata, Mapping) else {}
    candidate = metadata.get("opponent_profile_id") or metadata.get("npc_profile_id")
    if isinstance(candidate, str) and candidate:
        try:
            return registry.by_id(candidate)
        except KeyError:
            pass
    opponent_role = Role.SELLER if role == Role.BUYER else Role.BUYER
    profiles = registry.for_role(opponent_role)
    return profiles[0] if profiles else None


def _derive_lessons(
    run: LoadedRun,
    role: Role,
    opponent_profile: StrategyProfile | None,
) -> list[PolicyLesson]:
    lessons: list[PolicyLesson] = []
    metrics = run.metrics.metrics
    tool_calls = _events(run.trace, role=role, action_type=ActionType.TOOL_CALL)
    tool_failures = [event for event in tool_calls if event.tool_result and event.tool_result.get("ok") is False]
    own_offers = _events(run.trace, role=role, action_type=ActionType.OFFER)

    if run.metrics.outcome != "deal":
        lessons.append(
            PolicyLesson(
                id="no_deal_recovery",
                severity="high",
                category="deal_failure",
                finding=f"The run ended with outcome={run.metrics.outcome!r}, so the strategy did not close a transaction.",
                recommendation=(
                    "Add an explicit late-turn recovery policy: identify the counterparty's last acceptable "
                    "range, make one bounded concession, and either close or reject before timeout."
                ),
                evidence=_evidence_refs(run.trace[-3:]),
                suggested_strategy_patch=(
                    "When max_turns is near exhaustion, switch from exploration to close mode: "
                    "make the best justified offer inside budget/reservation, then ask for accept/reject."
                ),
            )
        )

    if role == Role.BUYER:
        lessons.extend(_buyer_lessons(run, own_offers, tool_calls))
    else:
        lessons.extend(_seller_lessons(run, own_offers))

    if tool_failures:
        lessons.append(
            PolicyLesson(
                id="tool_failure_fallback",
                severity="medium",
                category="tool_use",
                finding=f"{len(tool_failures)} tool call(s) failed or returned unusable evidence.",
                recommendation=(
                    "Add a fallback policy for stale, noisy, or failed tools: use listing price, prior comps, "
                    "and explicit uncertainty instead of continuing as if the tool succeeded."
                ),
                evidence=_evidence_refs(tool_failures[:3]),
                suggested_strategy_patch=(
                    "If market evidence fails, state uncertainty, lower confidence, and make a conservative "
                    "bounded offer rather than anchoring on missing data."
                ),
            )
        )

    if opponent_profile and opponent_profile.expected_traps:
        triggered = _triggered_profile_traps(run, role, opponent_profile)
        if triggered:
            lessons.append(
                PolicyLesson(
                    id="opponent_trap_awareness",
                    severity="medium",
                    category="opponent_modeling",
                    finding=(
                        f"The opponent profile {opponent_profile.id!r} is designed to test: "
                        + "; ".join(triggered)
                    ),
                    recommendation=(
                        "Represent the opponent archetype in strategy memory and choose a counter-policy "
                        "before making the next offer."
                    ),
                    evidence=_evidence_refs(_events(run.trace, role=Role.SELLER if role == Role.BUYER else Role.BUYER)[:3]),
                    suggested_strategy_patch=(
                        "Before responding, classify the opponent's current tactic and name the countermeasure "
                        "you are applying."
                    ),
                )
            )

    if not lessons:
        lessons.append(
            PolicyLesson(
                id="tighten_success_policy",
                severity="low",
                category="optimization",
                finding="The run completed without a major deterministic failure signal.",
                recommendation=(
                    "Keep the core strategy but add a post-deal audit: compare final price against market "
                    "reference and transaction costs to tighten future concessions."
                ),
                evidence=_evidence_refs(run.trace[-2:]),
                suggested_strategy_patch=(
                    "After any accepted deal, record market gap and transaction costs as examples for future "
                    "offer calibration."
                ),
            )
        )
    return lessons


def _buyer_lessons(
    run: LoadedRun,
    own_offers: Sequence[TraceEventRecord],
    tool_calls: Sequence[TraceEventRecord],
) -> list[PolicyLesson]:
    lessons = []
    market = run.scenario.product.market_reference
    deal_price = run.metrics.deal_price
    metrics = run.metrics.metrics
    tool_regime = run.manifest.tool_regime
    has_available_market_tool = "market_price_search" in json.dumps(to_jsonable(tool_regime))

    if has_available_market_tool and not tool_calls:
        lessons.append(
            PolicyLesson(
                id="missed_market_tool",
                severity="high",
                category="tool_use",
                finding="The buyer had market evidence available but made offers without calling it.",
                recommendation=(
                    "Call market_price_search before the first binding offer, then anchor the offer to sold "
                    "comparables instead of the seller's listing price."
                ),
                evidence=_evidence_refs(own_offers[:2]),
                suggested_strategy_patch=(
                    "Before the first offer, search recent sold comps for the exact product and condition; "
                    "use the median and IQR as the negotiation anchor."
                ),
            )
        )

    if deal_price is not None and market is not None and deal_price > market.reference_price * 1.05:
        lessons.append(
            PolicyLesson(
                id="buyer_overpaid_market",
                severity="high",
                category="price_discipline",
                finding=(
                    f"The accepted price ${deal_price:.2f} is more than 5% above the market reference "
                    f"${market.reference_price:.2f}."
                ),
                recommendation=(
                    "Cap final buyer offers at the market reference unless the trace records a concrete "
                    "quality, shipping, warranty, or urgency reason."
                ),
                evidence=_evidence_refs(_accepted_or_final_offer(run.trace)),
                suggested_strategy_patch=(
                    "Never exceed market_reference * 1.05 unless a written exception is justified by "
                    "condition, bundle value, or time preference."
                ),
            )
        )

    transaction_events = _events(run.trace, action_type=ActionType.TRANSACTION)
    if (
        transaction_events
        and metrics.get("transaction_completed_rate", 0.0) == 0.0
        and run.metrics.outcome == "deal"
    ):
        lessons.append(
            PolicyLesson(
                id="transaction_risk_ignored",
                severity="medium",
                category="transaction_risk",
                finding="The negotiation reached a deal but did not complete settlement.",
                recommendation=(
                    "Account for shipping, tax, escrow, payment, seller fees, and failure risk before accepting."
                ),
                evidence=_evidence_refs(transaction_events[-2:]),
                suggested_strategy_patch=(
                    "Before accept, compute buyer_total_cost and reject deals whose all-in cost exceeds budget."
                ),
            )
        )
    return lessons


def _seller_lessons(
    run: LoadedRun,
    own_offers: Sequence[TraceEventRecord],
) -> list[PolicyLesson]:
    lessons = []
    deal_price = run.metrics.deal_price
    reservation = run.scenario.seller_reservation_price
    market = run.scenario.product.market_reference
    if deal_price is not None and deal_price < reservation:
        lessons.append(
            PolicyLesson(
                id="seller_below_reservation",
                severity="high",
                category="price_discipline",
                finding=f"The seller accepted ${deal_price:.2f}, below reservation ${reservation:.2f}.",
                recommendation="Hard-code reservation checks before accept and before counter-offer generation.",
                evidence=_evidence_refs(_accepted_or_final_offer(run.trace)),
                suggested_strategy_patch="Never accept or counter below reservation_price.",
            )
        )
    if deal_price is not None and market is not None and deal_price < market.reference_price * 0.9:
        lessons.append(
            PolicyLesson(
                id="seller_undersold_market",
                severity="medium",
                category="price_discipline",
                finding=(
                    f"The accepted price ${deal_price:.2f} is more than 10% below the market reference "
                    f"${market.reference_price:.2f}."
                ),
                recommendation="Use market reference as a concession floor unless inventory risk justifies discounting.",
                evidence=_evidence_refs(own_offers[-2:]),
                suggested_strategy_patch=(
                    "Do not concede below 0.9 * market_reference unless the product has a disclosed defect "
                    "or stale inventory pressure."
                ),
            )
        )
    return lessons


def _derive_strengths(run: LoadedRun, role: Role) -> list[str]:
    strengths = []
    metrics = run.metrics.metrics
    if run.metrics.outcome == "deal":
        strengths.append("Closed a deal instead of timing out.")
    if metrics.get("tool_call_count", 0.0) > 0:
        strengths.append("Used available tools and preserved trace evidence.")
    if metrics.get("tool_failure_count", 0.0) == 0.0 and metrics.get("tool_call_count", 0.0) > 0:
        strengths.append("Tool calls completed without recorded failures.")
    if role == Role.BUYER and metrics.get("buyer_savings_rate", 0.0) > 0:
        strengths.append("Negotiated below the buyer budget.")
    if role == Role.SELLER and metrics.get("seller_profit_rate", 0.0) > 0:
        strengths.append("Preserved seller margin over reservation.")
    return strengths or ["No major strength signal was detected by deterministic heuristics."]


def _policy_score(run: LoadedRun, lessons: Sequence[PolicyLesson]) -> float:
    score = 100.0
    for lesson in lessons:
        if lesson.severity == "high":
            score -= 25.0
        elif lesson.severity == "medium":
            score -= 12.5
        else:
            score -= 4.0
    if run.metrics.outcome == "deal":
        score += 10.0
    return round(max(0.0, min(100.0, score)), 1)


def _summary(
    run: LoadedRun,
    role: Role,
    opponent_profile: StrategyProfile | None,
    score: float,
    lessons: Sequence[PolicyLesson],
) -> str:
    opponent = opponent_profile.name if opponent_profile else "the opponent"
    issue_count = sum(1 for lesson in lessons if lesson.severity in {"high", "medium"})
    deal = f" at ${run.metrics.deal_price:.2f}" if run.metrics.deal_price is not None else ""
    return (
        f"As {role.value}, the agent ended with outcome={run.metrics.outcome}{deal} "
        f"against {opponent}. Policy score={score:.1f}. "
        f"Detected {issue_count} actionable issue(s) for strategy optimization."
    )


def _suggested_strategy_prompt(role: Role, lessons: Sequence[PolicyLesson]) -> str:
    lines = [
        f"Role strategy patch for {role.value}:",
        f"Keep {PRODUCT_NAME} base protocol fixed. Edit only the strategy layer.",
    ]
    for index, lesson in enumerate(lessons, start=1):
        if lesson.suggested_strategy_patch:
            lines.append(f"{index}. {lesson.suggested_strategy_patch}")
    return "\n".join(lines)


def _triggered_profile_traps(
    run: LoadedRun,
    role: Role,
    profile: StrategyProfile,
) -> tuple[str, ...]:
    triggered = []
    text = " ".join(
        event.content
        for event in run.trace
        if event.role != role and event.content
    ).lower()
    for trap in profile.expected_traps:
        lowered = trap.lower()
        if "anchor" in lowered and _events(run.trace, role=profile.role, action_type=ActionType.OFFER):
            triggered.append(trap)
        elif "tool" in lowered and "tool" in text:
            triggered.append(trap)
        elif "transaction" in lowered and run.metrics.metrics.get("transaction_completed_rate", 0.0) == 0.0:
            triggered.append(trap)
    return tuple(triggered)


def _events(
    trace: Sequence[TraceEventRecord],
    *,
    role: Role | None = None,
    action_type: ActionType | None = None,
) -> list[TraceEventRecord]:
    return [
        event
        for event in trace
        if (role is None or event.role == role)
        and (action_type is None or event.action_type == action_type)
    ]


def _accepted_or_final_offer(trace: Sequence[TraceEventRecord]) -> list[TraceEventRecord]:
    accepted = _events(trace, action_type=ActionType.ACCEPT)
    offers = _events(trace, action_type=ActionType.OFFER)
    return [*offers[-2:], *accepted[-1:]]


def _evidence_refs(events: Sequence[TraceEventRecord]) -> tuple[EvidenceRef, ...]:
    return tuple(
        EvidenceRef(
            event_index=event.event_index,
            turn=event.turn,
            role=event.role,
            action_type=event.action_type,
            summary=_event_summary(event),
        )
        for event in events
    )


def _event_summary(event: TraceEventRecord) -> str:
    parts = [f"{event.role.value} {event.action_type.value}"]
    if event.offer is not None:
        parts.append(f"offer=${event.offer.price:.2f}")
    if event.tool_call is not None:
        parts.append(f"tool={event.tool_call.name}")
    if event.tool_result is not None:
        if event.tool_result.get("ok") is False:
            parts.append(f"tool_error={event.tool_result.get('error', 'unknown')}")
        elif event.tool_result.get("median_price") is not None:
            parts.append(f"median=${float(event.tool_result['median_price']):.2f}")
    if event.transaction is not None:
        parts.append(f"transaction={event.transaction.status}")
    if event.content:
        parts.append(_truncate(event.content, 80))
    return " | ".join(parts)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key}: expected non-empty string")
    return value


def _optional_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{key}: expected object")
    return value
