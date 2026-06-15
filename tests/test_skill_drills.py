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


def test_walkaway_drill_is_deterministic():
    from opennego.skill_drills import run_walkaway_drill

    a = run_walkaway_drill(seed=5, patience=1)
    b = run_walkaway_drill(seed=5, patience=1)
    assert a.score == b.score
    assert a.unwinnable_outcome == b.unwinnable_outcome


def test_decisive_policy_walks_unwinnable_without_timeout():
    from opennego.skill_drills import run_walkaway_drill

    decisive = run_walkaway_drill(seed=5, patience=1)
    assert decisive.unwinnable_outcome in {"rejected", "ghosted"}
    assert decisive.walk_score > 0.0


def test_patient_policy_times_out_unwinnable():
    from opennego.skill_drills import run_walkaway_drill

    patient = run_walkaway_drill(seed=5, patience=50, max_turns=8)
    assert patient.unwinnable_outcome == "timeout"
    assert patient.walk_score == 0.0


def test_decisive_beats_patient_overall():
    from opennego.skill_drills import run_walkaway_drill

    decisive = run_walkaway_drill(seed=5, patience=1)
    patient = run_walkaway_drill(seed=5, patience=50)
    assert decisive.score > patient.score


def test_walkaway_cli(capsys):
    code = main(["drill", "walkaway", "--seed", "9", "--patience", "1"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["drill"] == "walkaway"
    assert "walk_score" in payload and "stay_score" in payload


def test_multithread_drill_is_deterministic():
    from opennego.skill_drills import run_multithread_drill

    a = run_multithread_drill(seed=4, thread_count=3)
    b = run_multithread_drill(seed=4, thread_count=3)
    assert a.score == b.score
    assert a.closed_prices == b.closed_prices


def test_coordination_never_worse_and_often_better():
    from opennego.skill_drills import run_multithread_drill

    strictly_better = 0
    for seed in range(20):
        coord = run_multithread_drill(seed=seed, coordinate=True)
        indep = run_multithread_drill(seed=seed, coordinate=False)
        assert coord.score >= indep.score - 1e-9
        strictly_better += coord.score > indep.score
    # Shopping across threads should win outright on a meaningful share.
    assert strictly_better >= 5


def test_multithread_coordinated_takes_best_close():
    from opennego.skill_drills import run_multithread_drill

    result = run_multithread_drill(seed=5, coordinate=True)
    if result.closed_prices:
        assert result.closed_price == min(result.closed_prices)


def test_multithread_requires_two_threads():
    from opennego.skill_drills import SkillDrillError, run_multithread_drill

    with pytest.raises(SkillDrillError, match="thread_count"):
        run_multithread_drill(seed=1, thread_count=1)


def test_multithread_cli(capsys):
    code = main(["drill", "multithread", "--seed", "0", "--thread-count", "3"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["drill"] == "multithread"
    assert payload["coordinated"] is True
