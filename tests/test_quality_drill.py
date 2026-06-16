"""Quality-elicitation skill drill (#204)."""

import json

import pytest

from opennego.skill_drills import (
    SKILL_DRILL_SCHEMA_VERSION,
    SkillDrillError,
    run_quality_drill,
)


def test_inspecting_buyer_beats_face_value_on_the_lemon():
    result = run_quality_drill(seed=13)
    assert result.drill == "quality_elicitation"
    assert result.schema_version == SKILL_DRILL_SCHEMA_VERSION
    assert result.inspect_score > result.face_value_score
    assert result.elicitation_edge > 0.0
    assert result.score == result.inspect_score
    # The inspecting buyer closes well below the face-value buyer on the lemon.
    assert result.inspect_deal_price is not None
    assert result.face_value_deal_price is not None
    assert result.inspect_deal_price < result.face_value_deal_price


def test_edge_holds_across_seeds():
    for seed in (1, 7, 42, 99):
        result = run_quality_drill(seed=seed)
        assert result.elicitation_edge > 0.0


def test_deterministic_given_seed():
    a = run_quality_drill(seed=21)
    b = run_quality_drill(seed=21)
    assert a == b


def test_rejects_out_of_range_true_quality():
    with pytest.raises(SkillDrillError):
        run_quality_drill(true_quality=1.5)


def test_writes_artifact(tmp_path):
    out = tmp_path / "quality_drill.json"
    run_quality_drill(seed=3, output_path=out)
    payload = json.loads(out.read_text())
    assert payload["schema_version"] == SKILL_DRILL_SCHEMA_VERSION
    assert payload["drill"] == "quality_elicitation"
    assert payload["claimed_quality"] == 0.9
