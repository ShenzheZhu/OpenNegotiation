"""Reputation skill drill (#212)."""

import json

import pytest

from opennego.skill_drills import (
    SKILL_DRILL_SCHEMA_VERSION,
    run_reputation_drill,
)


def test_aware_buyer_beats_blind_buyer_against_low_rep_seller():
    result = run_reputation_drill(seed=13, band="low")
    assert result.drill == "reputation"
    assert result.schema_version == SKILL_DRILL_SCHEMA_VERSION
    assert result.band == "low"
    assert result.aware_score > result.blind_score
    assert result.reputation_edge > 0.0
    assert result.score == result.aware_score
    assert result.aware_deal_price is not None
    assert result.blind_deal_price is not None
    assert result.aware_deal_price < result.blind_deal_price


@pytest.mark.parametrize("band", ["low", "medium", "unknown"])
def test_edge_positive_for_risky_bands(band):
    assert run_reputation_drill(band=band).reputation_edge > 0.0


def test_high_reputation_has_no_edge():
    # A high-reputation seller carries no risk weight, so discounting is a no-op.
    result = run_reputation_drill(band="high")
    assert result.reputation_edge == 0.0


def test_deterministic():
    assert run_reputation_drill(seed=5) == run_reputation_drill(seed=5)


def test_writes_artifact(tmp_path):
    out = tmp_path / "reputation_drill.json"
    run_reputation_drill(seed=3, output_path=out)
    payload = json.loads(out.read_text())
    assert payload["schema_version"] == SKILL_DRILL_SCHEMA_VERSION
    assert payload["drill"] == "reputation"
    assert payload["band"] == "low"


def test_cli_runs():
    from opennego.cli.drills import drill_main

    assert drill_main(["reputation", "--band", "low"]) == 0
