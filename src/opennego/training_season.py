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

from opennego.artifacts import read_json
from opennego.coaching import PHASES, SEVERITIES, BattleReport

WEAKNESS_PROFILE_SCHEMA_VERSION = "opennego.weakness_profile.v1"

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
