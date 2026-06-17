"""Training season: aggregate weaknesses across a whole sparring roster.

The single-shot training loop (``opennego.training.run_training_loop``) patches
from one opponent's battle report. A season instead reads every report from a
sparring suite and aggregates the coach's findings by ``(phase, category)`` into
a ranked weakness profile — the diagnostic that drives the validated candidate
slate (see ``docs/design/training_season.md``).

This module is deterministic and no-key: it consumes battle reports that the
rule-based coach already produced.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from opennego.artifacts import read_json, to_jsonable, write_json
from opennego.coaching import PHASES, SEVERITIES, BattleReport
from opennego.evolution import load_strategy_candidate, write_strategy_candidate
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH
from opennego.schema import Role
from opennego.sparring import SparringSuiteSummary, run_sparring_suite
from opennego.strategy_config import write_strategy_config
from opennego.training import _generalization, split_opponent_roster

WEAKNESS_PROFILE_SCHEMA_VERSION = "opennego.weakness_profile.v1"
TRAINING_SEASON_SCHEMA_VERSION = "opennego.training_season.v1"
TRAINING_SEASON_EXECUTION_MODE = "weakness_aggregation_validated_slate_v1"

# Severity → numeric weight; mirrors the SEVERITIES order in coaching.
_SEVERITY_WEIGHT = {name: float(index + 1) for index, name in enumerate(SEVERITIES)}
_PHASE_ORDER = {name: index for index, name in enumerate(PHASES)}
_MAX_OPPONENTS = 5


class TrainingSeasonError(ValueError):
    """Raised when a season cannot be aggregated."""


@dataclass(frozen=True)
class AggregatedWeakness:
    phase: str
    category: str
    frequency: int
    severity_weight: float
    mean_policy_score: float
    priority: float
    opponents: tuple[str, ...]


@dataclass(frozen=True)
class WeaknessProfile:
    schema_version: str
    user_role: str
    matches_analyzed: int
    mean_policy_score: float
    weaknesses: tuple[AggregatedWeakness, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "WeaknessProfile":
        version = data.get("schema_version")
        if version != WEAKNESS_PROFILE_SCHEMA_VERSION:
            raise TrainingSeasonError(
                f"schema_version: expected {WEAKNESS_PROFILE_SCHEMA_VERSION!r}, "
                f"got {version!r}"
            )
        return cls(
            schema_version=WEAKNESS_PROFILE_SCHEMA_VERSION,
            user_role=str(data["user_role"]),
            matches_analyzed=int(data["matches_analyzed"]),
            mean_policy_score=float(data["mean_policy_score"]),
            weaknesses=tuple(
                AggregatedWeakness(
                    phase=str(item["phase"]),
                    category=str(item["category"]),
                    frequency=int(item["frequency"]),
                    severity_weight=float(item["severity_weight"]),
                    mean_policy_score=float(item["mean_policy_score"]),
                    priority=float(item["priority"]),
                    opponents=tuple(str(o) for o in item.get("opponents", ())),
                )
                for item in data.get("weaknesses", ())
            ),
        )


def aggregate_weaknesses(reports: Sequence[BattleReport]) -> WeaknessProfile:
    """Aggregate battle reports into a ranked weakness profile.

    Each weakness is keyed by ``(phase, category)`` — phase comes from the
    report's weakness, category from the matching lesson (joined by id). The
    priority rewards weaknesses that are frequent, severe, and appear in
    low-scoring matches: ``frequency * severity_weight * (1 - mean_score)``.
    """

    if not reports:
        raise TrainingSeasonError("no battle reports to aggregate")

    # Per-(phase, category) accumulators.
    freq: dict[tuple[str, str], int] = {}
    sev: dict[tuple[str, str], float] = {}
    score_sum: dict[tuple[str, str], float] = {}
    opponents: dict[tuple[str, str], list[str]] = {}

    for report in reports:
        category_by_id = {lesson.id: lesson.category for lesson in report.lessons}
        # A weakness counts once per report toward frequency even if the same
        # (phase, category) surfaces twice in that match.
        seen_keys: set[tuple[str, str]] = set()
        for weakness in report.weaknesses:
            category = category_by_id.get(weakness.id, "uncategorized")
            key = (weakness.phase, category)
            weight = _SEVERITY_WEIGHT.get(weakness.severity, 1.0)
            sev[key] = max(sev.get(key, 0.0), weight)
            if key not in seen_keys:
                seen_keys.add(key)
                freq[key] = freq.get(key, 0) + 1
                score_sum[key] = score_sum.get(key, 0.0) + report.score
                bucket = opponents.setdefault(key, [])
                opponent = report.opponent_profile_id or "unknown"
                if opponent not in bucket:
                    bucket.append(opponent)

    aggregated = []
    for key, frequency in freq.items():
        phase, category = key
        mean_score = score_sum[key] / frequency
        severity_weight = sev[key]
        priority = frequency * severity_weight * max(0.0, 1.0 - mean_score)
        aggregated.append(
            AggregatedWeakness(
                phase=phase,
                category=category,
                frequency=frequency,
                severity_weight=severity_weight,
                mean_policy_score=round(mean_score, 6),
                priority=round(priority, 6),
                opponents=tuple(sorted(opponents[key])[:_MAX_OPPONENTS]),
            )
        )

    aggregated.sort(
        key=lambda w: (
            -w.priority,
            _PHASE_ORDER.get(w.phase, len(_PHASE_ORDER)),
            w.category,
        )
    )

    scores = [report.score for report in reports]
    user_role = reports[0].user_role
    return WeaknessProfile(
        schema_version=WEAKNESS_PROFILE_SCHEMA_VERSION,
        user_role=user_role.value if hasattr(user_role, "value") else str(user_role),
        matches_analyzed=len(reports),
        mean_policy_score=round(sum(scores) / len(scores), 6),
        weaknesses=tuple(aggregated),
    )


def load_battle_reports(paths: Sequence[str | Path]) -> tuple[BattleReport, ...]:
    """Load battle reports from disk, skipping missing paths."""

    reports = []
    for path in paths:
        resolved = Path(path)
        if not resolved.exists():
            continue
        reports.append(BattleReport.from_mapping(read_json(resolved)))
    return tuple(reports)


@dataclass(frozen=True)
class CandidateSlateEntry:
    rank: int
    phase: str
    category: str
    candidate_id: str
    candidate_path: str
    strategy_config_path: str
    verdict: str
    train_score_delta: float
    heldout_score_delta: float
    rerun_mean_score: float
    generalizes: bool


@dataclass(frozen=True)
class TrainingSeason:
    schema_version: str
    execution_mode: str
    user_role: str
    output_dir: str
    train_profile_ids: tuple[str, ...]
    heldout_profile_ids: tuple[str, ...]
    baseline_mean_score: float
    weakness_profile: WeaknessProfile
    slate: tuple[CandidateSlateEntry, ...]
    recommended_candidate_id: str | None
    recommended_heldout_delta: float
    trajectory: Mapping[str, Any]
    artifact_path: str


def run_training_season(
    *,
    output_dir: str | Path = "runs/training_season",
    config_path: str | Path = "configs/real_market_demo.yaml",
    registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
    user_role: Role | str = Role.BUYER,
    k: int = 3,
    learning_tool_regime: str = "no_tools",
    holdout_seed: int = 0,
    parent_strategy_id: str = "user_strategy_v0",
    fail_fast: bool = True,
) -> TrainingSeason:
    """Run a full training season: aggregate, evolve a slate, validate, rank.

    Spars the whole opposite-role roster, aggregates the train-set weaknesses,
    and for the top-``k`` weaknesses generates a focused candidate, reruns the
    suite with it, and records its held-out generalization. Candidates are
    ranked with overfit (``train_only``/``regressed``) demoted below any that
    generalize. Nothing is applied — the recommendation is advisory.
    """

    if k < 1:
        raise TrainingSeasonError("k: expected at least one candidate")

    output = Path(output_dir)
    role = Role(user_role)
    train_ids, heldout_ids = split_opponent_roster(
        registry_path=registry_path, user_role=role, seed=holdout_seed
    )
    roster = tuple(dict.fromkeys(train_ids + heldout_ids))

    baseline = run_sparring_suite(
        output_dir=output / "baseline",
        config_path=config_path,
        registry_path=registry_path,
        user_role=role,
        opponent_profile_ids=roster,
        learning_tool_regime=learning_tool_regime,
        fail_fast=fail_fast,
    )

    train_set = set(train_ids)
    train_results = [
        result
        for result in baseline.results
        if result.status == "completed"
        and result.battle_report is not None
        and result.profile_id in train_set
    ]
    if not train_results:
        raise TrainingSeasonError("season requires at least one completed train report")

    report_by_path = {
        result.battle_report: BattleReport.from_mapping(read_json(result.battle_report))
        for result in train_results
    }
    profile = aggregate_weaknesses(tuple(report_by_path.values()))
    baseline_mean = _suite_mean_score(baseline)

    raw_entries: list[tuple[Any, float]] = []  # (entry-without-rank, sort score)
    rank_source = sorted(
        train_results, key=lambda r: (r.policy_score if r.policy_score is not None else 1.0)
    )
    candidate_index = 0
    for weakness in profile.weaknesses:
        if candidate_index >= k:
            break
        source = _find_source_report(rank_source, report_by_path, weakness)
        if source is None:
            continue  # no real lesson backs this weakness; cannot target it
        candidate_index += 1
        cand_dir = output / f"candidate_{candidate_index}"
        focused_path = cand_dir / "focused_battle_report.json"
        if not _write_focused_report(source, weakness, focused_path):
            candidate_index -= 1
            continue
        candidate_path = cand_dir / "strategy_candidate.json"
        write_strategy_candidate(
            focused_path,
            candidate_path,
            parent_strategy_id=parent_strategy_id,
            iteration=1,
        )
        config_out = cand_dir / "strategy_config.json"
        write_strategy_config(candidate_path, config_out)
        rerun = run_sparring_suite(
            output_dir=cand_dir / "rerun",
            config_path=config_path,
            registry_path=registry_path,
            user_role=role,
            opponent_profile_ids=roster,
            user_strategy_path=candidate_path,
            learning_tool_regime=learning_tool_regime,
            fail_fast=fail_fast,
        )
        gen = _generalization(
            baseline=baseline, rerun=rerun, train_ids=train_ids, heldout_ids=heldout_ids
        )
        heldout_delta = float(gen["held_out"]["mean_score_delta"])
        candidate = load_strategy_candidate(candidate_path)
        generalizes = gen["verdict"] == "improved" and heldout_delta > 0.0
        raw_entries.append(
            (
                {
                    "phase": weakness.phase,
                    "category": weakness.category,
                    "candidate_id": candidate.candidate_id,
                    "candidate_path": str(candidate_path),
                    "strategy_config_path": str(config_out),
                    "verdict": gen["verdict"],
                    "train_score_delta": float(gen["train"]["mean_score_delta"]),
                    "heldout_score_delta": heldout_delta,
                    "rerun_mean_score": _suite_mean_score(rerun),
                    "generalizes": generalizes,
                },
                heldout_delta,
            )
        )

    # Generalizing candidates first (by held-out delta desc), then the rest.
    raw_entries.sort(key=lambda item: (0 if item[0]["generalizes"] else 1, -item[1]))
    slate = tuple(
        CandidateSlateEntry(rank=index + 1, **fields)
        for index, (fields, _delta) in enumerate(raw_entries)
    )

    recommended = slate[0] if slate and slate[0].generalizes else None
    best_mean = recommended.rerun_mean_score if recommended else baseline_mean
    trajectory = {
        "baseline_mean_score": round(baseline_mean, 6),
        "best_mean_score": round(best_mean, 6),
        "delta": round(best_mean - baseline_mean, 6),
    }

    artifact_path = output / "training_season.json"
    season = TrainingSeason(
        schema_version=TRAINING_SEASON_SCHEMA_VERSION,
        execution_mode=TRAINING_SEASON_EXECUTION_MODE,
        user_role=role.value,
        output_dir=str(output),
        train_profile_ids=tuple(train_ids),
        heldout_profile_ids=tuple(heldout_ids),
        baseline_mean_score=round(baseline_mean, 6),
        weakness_profile=profile,
        slate=slate,
        recommended_candidate_id=recommended.candidate_id if recommended else None,
        recommended_heldout_delta=(
            recommended.heldout_score_delta if recommended else 0.0
        ),
        trajectory=trajectory,
        artifact_path=str(artifact_path),
    )
    write_json(artifact_path, to_jsonable(season))
    return season


def _suite_mean_score(summary: SparringSuiteSummary) -> float:
    scores = [
        result.policy_score
        for result in summary.results
        if result.status == "completed" and result.policy_score is not None
    ]
    return sum(scores) / len(scores) if scores else 0.0


def _report_matches(report: BattleReport, phase: str, category: str) -> bool:
    category_by_id = {lesson.id: lesson.category for lesson in report.lessons}
    return any(
        weakness.phase == phase
        and category_by_id.get(weakness.id, "uncategorized") == category
        for weakness in report.weaknesses
    )


def _find_source_report(
    ranked_results: Sequence[Any],
    report_by_path: Mapping[str, BattleReport],
    weakness: AggregatedWeakness,
) -> str | None:
    """Lowest-scoring train report that surfaced this weakness (path)."""

    for result in ranked_results:
        report = report_by_path.get(result.battle_report)
        if report is not None and _report_matches(
            report, weakness.phase, weakness.category
        ):
            return result.battle_report
    return None


def _write_focused_report(
    source_path: str, weakness: AggregatedWeakness, output_path: Path
) -> bool:
    """Write the source report filtered to one weakness's lessons.

    Returns False (and writes nothing) if no lesson backs the weakness, so the
    candidate generator is never handed an empty report.
    """

    raw = dict(read_json(source_path))
    lessons = [
        lesson
        for lesson in raw.get("lessons", ())
        if lesson.get("category") == weakness.category
    ]
    if not lessons:
        return False
    kept_ids = {lesson.get("id") for lesson in lessons}
    weaknesses = [
        item
        for item in raw.get("weaknesses", ())
        if item.get("phase") == weakness.phase and item.get("id") in kept_ids
    ]
    raw["lessons"] = lessons
    raw["weaknesses"] = weaknesses
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, raw)
    return True
