"""Training-season weakness aggregation (#221)."""

import json
from pathlib import Path

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


# --- season runner (#222) --------------------------------------------------


def test_run_training_season_produces_ranked_validated_slate(tmp_path):
    from opennego.training_season import (
        TRAINING_SEASON_SCHEMA_VERSION,
        run_training_season,
    )

    season = run_training_season(output_dir=tmp_path / "season", user_role="buyer", k=2)

    assert season.schema_version == TRAINING_SEASON_SCHEMA_VERSION
    assert season.user_role == "buyer"
    assert season.weakness_profile.matches_analyzed >= 1
    assert 1 <= len(season.slate) <= 2
    assert season.train_profile_ids and season.heldout_profile_ids

    # Ranks are sequential and every entry carries a held-out verdict.
    assert [e.rank for e in season.slate] == list(range(1, len(season.slate) + 1))
    for entry in season.slate:
        assert entry.verdict in {"improved", "train_only", "regressed"}
        assert (tmp_path / "season").as_posix() in entry.candidate_path
        assert Path(entry.candidate_path).exists()

    # Invariant: no overfit/regressed candidate is ranked above a generalizing one.
    generalizing_flags = [e.generalizes for e in season.slate]
    assert generalizing_flags == sorted(generalizing_flags, reverse=True)

    # The recommendation is exactly the top entry iff it generalizes.
    if season.recommended_candidate_id is not None:
        assert season.slate[0].generalizes
        assert season.recommended_candidate_id == season.slate[0].candidate_id
    else:
        assert not season.slate[0].generalizes

    # Artifact is written and self-describing.
    payload = json.loads((tmp_path / "season" / "training_season.json").read_text())
    assert payload["schema_version"] == TRAINING_SEASON_SCHEMA_VERSION
    assert "trajectory" in payload and "baseline_mean_score" in payload["trajectory"]


def test_run_training_season_rejects_bad_k(tmp_path):
    from opennego.training_season import TrainingSeasonError, run_training_season

    with pytest.raises(TrainingSeasonError):
        run_training_season(output_dir=tmp_path / "s", k=0)


def test_train_season_cli_runs_and_writes_report(tmp_path, capsys):
    from opennego.cli import COMMANDS
    from opennego.cli.learning import train_season_main
    from opennego.training_season import TRAINING_SEASON_SCHEMA_VERSION

    assert "train-season" in COMMANDS

    report = tmp_path / "season.html"
    rc = train_season_main(
        [
            "--output-dir",
            str(tmp_path / "season"),
            "--k",
            "1",
            "--report",
            str(report),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == TRAINING_SEASON_SCHEMA_VERSION
    assert payload["report"] == str(report)
    html = report.read_text()
    assert "Training season" in html and "Validated candidate slate" in html
