import json

import pytest

from opennego.cli import main
from opennego.market import build_market
from opennego.market_calibration import (
    MARKET_CALIBRATION_SCHEMA_VERSION,
    CalibrationError,
    calibrate_episode,
    load_reference,
    reference_from_sold_comps,
)
from opennego.market_runtime import run_market_episode

PRODUCTS = "examples/data/scenario_seed_products.json"
REFERENCE = "examples/data/market_calibration_reference.json"


def _episode(seed=7):
    state = build_market(PRODUCTS, seed=seed, listings_per_product=2)
    return run_market_episode(
        state, buyer_ids=["buyer_a", "buyer_b", "buyer_c"], shortlist_size=3, seed=seed
    )


def test_calibration_reports_per_metric_verdicts():
    report = calibrate_episode(_episode(), reference=load_reference(REFERENCE))
    assert report.schema_version == MARKET_CALIBRATION_SCHEMA_VERSION
    names = {m.metric for m in report.metrics}
    assert names == {"mean_clearing_price", "mean_rounds", "deal_rate"}
    assert report.status in {"calibrated", "off", "no_data"}


def test_tight_reference_is_within_tolerance():
    episode = _episode()
    # Build a reference straight from the sandbox so it should be calibrated.
    deal_prices = [
        t["deal_price"] for t in episode.threads
        if t["status"] == "deal" and t["deal_price"] is not None
    ]
    rounds = [
        t["completed_turns"] for t in episode.threads
        if t["status"] == "deal" and t.get("completed_turns") is not None
    ]
    resolved = [
        t for t in episode.threads
        if t["status"] in {"deal", "rejected", "timeout", "ghosted"}
    ]
    ref = reference_from_sold_comps(
        prices=deal_prices,
        mean_rounds=sum(rounds) / len(rounds),
        deal_rate=len(deal_prices) / len(resolved),
    )
    report = calibrate_episode(episode, reference=ref, tolerance=0.05)
    clearing = next(m for m in report.metrics if m.metric == "mean_clearing_price")
    assert clearing.verdict == "within_tolerance"
    assert report.status == "calibrated"


def test_far_reference_is_off():
    report = calibrate_episode(
        _episode(),
        reference={"mean_clearing_price": 50.0, "mean_rounds": 99.0, "deal_rate": 0.01},
        tolerance=0.1,
    )
    assert report.status == "off"
    assert any(m.verdict == "out_of_tolerance" for m in report.metrics)


def test_missing_reference_metric_is_no_data():
    report = calibrate_episode(_episode(), reference={"mean_clearing_price": 520.0})
    rounds = next(m for m in report.metrics if m.metric == "mean_rounds")
    assert rounds.verdict == "no_data"


def test_reference_from_sold_comps_requires_prices():
    with pytest.raises(CalibrationError, match="prices"):
        reference_from_sold_comps(prices=[], mean_rounds=3.0, deal_rate=0.5)


def test_calibration_is_deterministic(tmp_path):
    out = tmp_path / "cal.json"
    a = calibrate_episode(_episode(), reference=load_reference(REFERENCE), output_path=out)
    b = calibrate_episode(_episode(), reference=load_reference(REFERENCE))
    assert a.status == b.status
    assert [m.relative_error for m in a.metrics] == [m.relative_error for m in b.metrics]
    assert out.exists()


def test_market_calibrate_cli(tmp_path, capsys):
    out = tmp_path / "cal.json"
    code = main(
        [
            "market-calibrate",
            "--products-file", PRODUCTS,
            "--reference", REFERENCE,
            "--seed", "7",
            "--output", str(out),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code in (0, 1)  # exit reflects calibrated vs off
    assert payload["schema_version"] == MARKET_CALIBRATION_SCHEMA_VERSION
    assert out.exists()
