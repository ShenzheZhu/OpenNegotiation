import json

import pytest

from opennego.transactions import (
    FeeScheduleError,
    FixtureTransactionSimulator,
    available_fee_schedules,
    load_fee_schedule,
)
from opennego.ports import TransactionRequest
from opennego.runner import (
    ConfigValidationError,
    load_experiment_config,
    run_experiment_config,
)
from opennego.scenario_generator import generate_scenarios, load_products


def _settle(simulator, price=575.0):
    scenario = generate_scenarios(
        load_products("examples/data/real_market_products.json"), seed=13
    )[0]
    return simulator.settle(
        TransactionRequest(
            scenario=scenario,
            negotiated_price=price,
            accepting_role="buyer",
        )
    )


def test_curated_schedules_load_with_provenance():
    assert set(available_fee_schedules()) == {
        "ebay_us_2026_general",
        "paypal_gs_us_2026",
        "local_cash_pickup",
    }
    for schedule_id in available_fee_schedules():
        schedule = load_fee_schedule(schedule_id)
        assert schedule.source_url.startswith("https://")
        assert schedule.as_of


def test_ebay_schedule_settlement_math_matches_hand_computation():
    schedule = load_fee_schedule("ebay_us_2026_general")
    simulator = FixtureTransactionSimulator(
        shipping_cost=schedule.shipping_cost,
        tax_rate=schedule.tax_rate,
        seller_fee_tiers=schedule.seller_fee_tiers,
        seller_fee_fixed=schedule.seller_fee_fixed,
    )

    outcome = _settle(simulator, price=575.0)

    assert outcome.seller_fee == pytest.approx(575.0 * 0.1335 + 0.30, abs=0.01)
    assert outcome.tax == pytest.approx(575.0 * 0.0635, abs=0.01)
    assert outcome.buyer_total_cost == pytest.approx(
        575.0 + 12.0 + outcome.tax, abs=0.01
    )
    assert outcome.seller_net_revenue == pytest.approx(
        575.0 - outcome.seller_fee, abs=0.01
    )


def test_tiered_fee_crosses_band_boundary():
    schedule = load_fee_schedule("ebay_us_2026_general")
    simulator = FixtureTransactionSimulator(
        seller_fee_tiers=schedule.seller_fee_tiers,
        seller_fee_fixed=schedule.seller_fee_fixed,
    )

    outcome = _settle(simulator, price=8000.0)

    expected = 7500.0 * 0.1335 + 500.0 * 0.0235 + 0.30
    assert outcome.seller_fee == pytest.approx(expected, abs=0.01)


def test_paypal_schedule_charges_receiver_side_fee():
    schedule = load_fee_schedule("paypal_gs_us_2026")
    simulator = FixtureTransactionSimulator(
        seller_fee_rate=schedule.seller_fee_rate,
        seller_fee_fixed=schedule.seller_fee_fixed,
    )

    outcome = _settle(simulator, price=100.0)

    assert outcome.seller_fee == pytest.approx(100.0 * 0.0299 + 0.49, abs=0.01)
    assert outcome.payment_fee == 0.0


def test_schedule_without_provenance_is_rejected(tmp_path):
    bad = {
        "schema_version": "opennego.fee_schedule.v1",
        "schedules": {
            "mystery": {"platform": "x", "seller_fee_rate": 0.1}
        },
    }
    path = tmp_path / "schedules.json"
    path.write_text(json.dumps(bad))

    with pytest.raises(FeeScheduleError, match="provenance"):
        load_fee_schedule("mystery", schedules_file=path)


def _config_with_schedule(tmp_path, **transaction_overrides):
    transaction = {
        "kind": "fixture",
        "enabled": True,
        "schedule": "ebay_us_2026_general",
        **transaction_overrides,
    }
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "fee_schedule_smoke",
        "output_dir": str(tmp_path / "runs"),
        "seeds": [7],
        "agents": {
            "buyer": {"kind": "tool_aware_buyer"},
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": [
            {
                "id": "iphone",
                "products_file": "examples/data/real_market_products.json",
                "max_turns": 8,
            }
        ],
        "transaction": transaction,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


def test_runner_config_resolves_schedule_and_records_provenance(tmp_path):
    config_path = _config_with_schedule(tmp_path)

    summary = run_experiment_config(config_path)

    assert summary.completed == 1
    run_dir = tmp_path / "runs" / summary.runs[0].run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    transaction_meta = manifest["metadata"]["transaction"]
    assert transaction_meta["schedule"] == "ebay_us_2026_general"
    assert transaction_meta["schedule_as_of"] == "2026-01-15"
    assert transaction_meta["seller_fee_tiers"] == [[7500.0, 0.1335], [None, 0.0235]]
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["metrics"]["transaction_fees"] > 0


def test_explicit_config_values_override_schedule(tmp_path):
    config_path = _config_with_schedule(tmp_path, shipping_cost=0.0, tax_rate=0.0)

    config = load_experiment_config(config_path)

    assert config.transaction.shipping_cost == 0.0
    assert config.transaction.tax_rate == 0.0
    assert config.transaction.seller_fee_fixed == 0.30


def test_unknown_schedule_id_fails_config_validation(tmp_path):
    config_path = _config_with_schedule(tmp_path)
    raw = json.loads(config_path.read_text())
    raw["transaction"]["schedule"] = "nonexistent"
    config_path.write_text(json.dumps(raw))

    with pytest.raises(ConfigValidationError, match="transaction.schedule"):
        load_experiment_config(config_path)
