"""Training-season weakness aggregation (#221)."""

import json

import pytest

from opennego.artifacts import to_jsonable, write_json
from opennego.coaching import BattleReport, PolicyLesson, Weakness
from opennego.schema import Role
from opennego.training_season import (
    WEAKNESS_PROFILE_SCHEMA_VERSION,
    TrainingSeasonError,
    WeaknessProfile,
    aggregate_weaknesses,
    load_battle_reports,
)


def _lesson(lid, category, severity="medium"):
    return PolicyLesson(
        id=lid,
        severity=severity,
        category=category,
        finding=f"finding for {lid}",
        recommendation=f"fix {lid}",
    )


def _weakness(lid, phase, severity="medium"):
    return Weakness(id=lid, phase=phase, severity=severity, summary=f"weak {lid}")


def _report(opponent, score, items):
    """items: list of (id, phase, category, severity)."""
    lessons = tuple(_lesson(i, c, s) for (i, _p, c, s) in items)
    weaknesses = tuple(_weakness(i, p, s) for (i, p, _c, s) in items)
    return BattleReport(
        schema_version="opennego.battle_report.v2",
        run_id=f"run-{opponent}",
        scenario_id="s1",
        user_role=Role.BUYER,
        opponent_profile_id=opponent,
        outcome="deal",
        deal_price=100.0,
        score=score,
        summary="s",
        failure_modes=(),
        strengths=(),
        lessons=lessons,
        suggested_strategy_prompt="p",
        artifacts={},
        weaknesses=weaknesses,
    )


def test_empty_raises():
    with pytest.raises(TrainingSeasonError):
        aggregate_weaknesses([])


def test_frequent_severe_weakness_outranks_rare_mild_one():
    # "closing over-concession" appears in 3 low-scoring matches at high severity;
    # "selection nitpick" appears once at low severity in a high-scoring match.
    reports = [
        _report("a", 0.2, [("L1", "closing", "concession_discipline", "high")]),
        _report("b", 0.25, [("L1", "closing", "concession_discipline", "high")]),
        _report(
            "c",
            0.3,
            [
                ("L1", "closing", "concession_discipline", "high"),
                ("L2", "selection", "tool_use", "low"),
            ],
        ),
        _report("d", 0.9, [("L2", "selection", "tool_use", "low")]),
    ]
    profile = aggregate_weaknesses(reports)
    assert profile.matches_analyzed == 4
    top = profile.weaknesses[0]
    assert (top.phase, top.category) == ("closing", "concession_discipline")
    assert top.frequency == 3
    assert top.severity_weight == 3.0  # high
    assert top.opponents == ("a", "b", "c")
    # The rare, mild, high-scoring weakness ranks last.
    last = profile.weaknesses[-1]
    assert (last.phase, last.category) == ("selection", "tool_use")
    assert top.priority > last.priority


def test_frequency_counts_once_per_report():
    # Same (phase, category) twice in one report counts as frequency 1.
    reports = [
        _report(
            "a",
            0.4,
            [
                ("L1", "negotiation", "anchoring", "medium"),
                ("L2", "negotiation", "anchoring", "high"),
            ],
        )
    ]
    profile = aggregate_weaknesses(reports)
    weak = profile.weaknesses[0]
    assert weak.frequency == 1
    assert weak.severity_weight == 3.0  # max(medium, high)
    assert weak.mean_policy_score == 0.4


def test_round_trips_through_artifact(tmp_path):
    reports = [_report("a", 0.5, [("L1", "closing", "concession_discipline", "high")])]
    profile = aggregate_weaknesses(reports)
    payload = json.loads(json.dumps(to_jsonable(profile)))
    restored = WeaknessProfile.from_mapping(payload)
    assert restored == profile
    assert restored.schema_version == WEAKNESS_PROFILE_SCHEMA_VERSION


def test_load_battle_reports_skips_missing(tmp_path):
    report = _report("a", 0.5, [("L1", "closing", "concession_discipline", "high")])
    path = tmp_path / "battle_report.json"
    write_json(path, to_jsonable(report))
    loaded = load_battle_reports([path, tmp_path / "missing.json"])
    assert len(loaded) == 1
    assert loaded[0].opponent_profile_id == "a"
