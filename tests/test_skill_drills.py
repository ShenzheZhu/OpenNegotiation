import json

import pytest

from opennego.cli import main
from opennego.skill_drills import (
    SKILL_DRILL_SCHEMA_VERSION,
    SkillDrillError,
    generate_selection_drill,
    lowest_asking_policy,
    risk_aware_policy,
    run_selection_drill,
    score_selection,
)


def test_drill_is_deterministic_by_seed():
    a = generate_selection_drill(seed=7, count=6)
    b = generate_selection_drill(seed=7, count=6)
    assert [l.attainable_surplus for l in a.listings] == [
        l.attainable_surplus for l in b.listings
    ]
    assert a.optimal_index == b.optimal_index


def test_cards_hide_ground_truth_surplus():
    drill = generate_selection_drill(seed=7, count=5)
    for card in drill.cards():
        assert "attainable_surplus" not in card
        assert "market_reference" in card


def test_picking_optimal_scores_one_worse_scores_lower():
    drill = generate_selection_drill(seed=7, count=6)
    best = drill.optimal_index
    assert score_selection(drill, best) == 1.0
    worst = min(
        range(len(drill.listings)),
        key=lambda i: drill.listings[i].attainable_surplus,
    )
    if drill.listings[worst].attainable_surplus < drill.listings[best].attainable_surplus:
        assert score_selection(drill, worst) < 1.0


def test_risk_aware_policy_beats_lowest_asking_on_average():
    aware_total = 0.0
    naive_total = 0.0
    for seed in range(40):
        drill = generate_selection_drill(seed=seed, count=6)
        aware_total += score_selection(drill, risk_aware_policy(drill.cards()))
        naive_total += score_selection(drill, lowest_asking_policy(drill.cards()))
    # The trap (cheap + low-reputation) listings should punish naive chasing.
    assert aware_total > naive_total


def test_run_selection_drill_writes_artifact(tmp_path):
    out = tmp_path / "drill.json"
    result = run_selection_drill(seed=13, output_path=out)

    assert result.schema_version == SKILL_DRILL_SCHEMA_VERSION
    assert result.drill == "listing_selection"
    assert 0.0 <= result.score <= 1.0
    payload = json.loads(out.read_text())
    assert payload["policy"] == "risk_aware"
    assert "chosen_index" in payload


def test_custom_policy_is_accepted():
    result = run_selection_drill(seed=3, policy=lambda cards: 0)
    assert result.chosen_index == 0


def test_unknown_policy_rejected():
    with pytest.raises(SkillDrillError, match="unknown policy"):
        run_selection_drill(seed=3, policy="nope")


def test_drill_cli(capsys):
    code = main(["drill", "select", "--seed", "21", "--policy", "risk_aware"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["drill"] == "listing_selection"
    assert payload["seed"] == 21
