"""Co-evolution tournament + generational engine (#230)."""

import json

import pytest

from opennego.coevolution import (
    COEVOLUTION_SCHEMA_VERSION,
    CoevolutionError,
    run_coevolution,
)


def _run(tmp_path, **kw):
    params = dict(
        output_dir=tmp_path / "coevo",
        generations=3,
        population=4,
        scenario_count=1,
        seed=7,
    )
    params.update(kw)
    return run_coevolution(**params)


def test_structure_and_artifact(tmp_path):
    result = _run(tmp_path)
    assert result.schema_version == COEVOLUTION_SCHEMA_VERSION
    assert len(result.generation_records) == 3
    for record in result.generation_records:
        assert len(record.buyer_leaderboard) == 4
        assert len(record.seller_leaderboard) == 4
        # Leaderboards are sorted by fitness desc.
        buyer_fits = [s.fitness for s in record.buyer_leaderboard]
        assert buyer_fits == sorted(buyer_fits, reverse=True)
    # Champions are the top of the final generation.
    final = result.generation_records[-1]
    assert result.buyer_champion.genome_id == final.buyer_leaderboard[0].genome_id
    assert result.seller_champion.genome_id == final.seller_leaderboard[0].genome_id

    payload = json.loads((tmp_path / "coevo" / "coevolution.json").read_text())
    assert payload["schema_version"] == COEVOLUTION_SCHEMA_VERSION
    assert len(payload["trajectory"]["buyer_best_by_generation"]) == 3


def test_deterministic_given_seed(tmp_path):
    a = _run(tmp_path / "a")
    b = _run(tmp_path / "b")
    assert a.trajectory == b.trajectory
    assert a.buyer_champion.genes == b.buyer_champion.genes
    assert a.seller_champion.genes == b.seller_champion.genes


def test_fixing_one_side_makes_the_other_improve_monotonically(tmp_path):
    # With sellers held fixed, surviving buyer elites are re-scored against the
    # same opponents, so the buyer best fitness can only hold or rise.
    result = _run(tmp_path, evolve=("buyer",), generations=4)
    best = result.trajectory["buyer_best_by_generation"]
    assert best == sorted(best)
    assert result.evolve_roles == ("buyer",)


def test_champion_lineage_chains_to_a_seed(tmp_path):
    result = _run(tmp_path, generations=4)
    lineage_ids = {entry["genome_id"] for entry in result.buyer_champion_lineage}
    assert any(gid.startswith("g0-") for gid in lineage_ids)


def test_rejects_bad_params(tmp_path):
    with pytest.raises(CoevolutionError):
        _run(tmp_path, population=1)
    with pytest.raises(CoevolutionError):
        _run(tmp_path, generations=0)
    with pytest.raises(CoevolutionError):
        _run(tmp_path, evolve=("referee",))
