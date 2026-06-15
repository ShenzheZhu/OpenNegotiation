import json

import pytest

from opennego.cli import main
from opennego.market import build_market
from opennego.market_autonomy import (
    MARKET_AUTONOMY_SCHEMA_VERSION,
    run_autonomy_episode,
)
from opennego.market_runtime import MarketRuntimeError

PRODUCTS = "examples/data/scenario_seed_products.json"


def _market(seed=7):
    return build_market(PRODUCTS, seed=seed, listings_per_product=2)


@pytest.mark.parametrize("level", ["L1", "L2", "L3"])
def test_each_level_runs_with_a_metric(level):
    result = run_autonomy_episode(_market(), buyer_id="buyer_a", level=level, seed=7)
    assert result.schema_version == MARKET_AUTONOMY_SCHEMA_VERSION
    assert result.level == level
    assert 0.0 <= result.score <= 1.0


def test_l1_engages_one_listing_l3_engages_many():
    l1 = run_autonomy_episode(_market(), buyer_id="b", level="L1", seed=7)
    l3 = run_autonomy_episode(
        _market(), buyer_id="b", level="L3", seed=7, shortlist_size=3
    )
    assert len(l1.engaged_listings) == 1
    assert len(l3.engaged_listings) >= len(l1.engaged_listings)


def test_l2_records_the_shortlist_it_chose_from():
    l2 = run_autonomy_episode(
        _market(), buyer_id="b", level="L2", seed=7, shortlist_size=3
    )
    assert l2.shortlist
    assert len(l2.engaged_listings) == 1
    assert l2.engaged_listings[0] in l2.shortlist


def test_autonomy_is_deterministic():
    a = run_autonomy_episode(_market(), buyer_id="b", level="L3", seed=7)
    b = run_autonomy_episode(_market(), buyer_id="b", level="L3", seed=7)
    assert a.score == b.score
    assert a.engaged_listings == b.engaged_listings


def test_invalid_level_rejected():
    with pytest.raises(MarketRuntimeError, match="level"):
        run_autonomy_episode(_market(), buyer_id="b", level="L9")


def test_autonomy_cli(tmp_path, capsys):
    out = tmp_path / "autonomy.json"
    code = main(
        [
            "market-run",
            "--products-file", PRODUCTS,
            "--seed", "7",
            "--buyer", "buyer_a",
            "--level", "L2",
            "--output", str(out),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["schema_version"] == MARKET_AUTONOMY_SCHEMA_VERSION
    assert payload["level"] == "L2"
    assert out.exists()
