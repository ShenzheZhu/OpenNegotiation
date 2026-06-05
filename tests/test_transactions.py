import json

import pytest

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import load_manifest, load_metric_report, load_trace
from opennego.environment import NegotiationEnvironment
from opennego.ports import TransactionRequest
from opennego.schema import ActionType, Product, Scenario
from opennego.tools import MarketComparable, MarketPriceTool
from opennego.runner import run_experiment_config
from opennego.transactions import FixtureTransactionSimulator


def make_scenario() -> Scenario:
    product = Product(
        id="camera_001",
        name="Sony Alpha a6400 Mirrorless Camera Body",
        description="Used mirrorless camera body.",
        condition="used",
        list_price=1000.0,
        wholesale_price=620.0,
    )
    return Scenario(
        product=product,
        buyer_budget=850.0,
        seller_reservation_price=620.0,
        max_turns=6,
    )


def make_market_tool() -> MarketPriceTool:
    return MarketPriceTool(
        [
            MarketComparable(
                query="Sony Alpha a6400 Mirrorless Camera Body",
                title="Sony a6400 body only",
                price=790.0,
                source="fixture",
                condition="used",
            ),
            MarketComparable(
                query="Sony Alpha a6400 Mirrorless Camera Body",
                title="Sony a6400 with battery",
                price=800.0,
                source="fixture",
                condition="used",
            ),
            MarketComparable(
                query="Sony Alpha a6400 Mirrorless Camera Body",
                title="Sony Alpha a6400 lightly used",
                price=810.0,
                source="fixture",
                condition="used",
            ),
        ]
    )


def make_transaction_simulator(payment_success: bool = True) -> FixtureTransactionSimulator:
    return FixtureTransactionSimulator(
        shipping_cost=18.0,
        tax_rate=0.08,
        escrow_fee=4.0,
        payment_fee_rate=0.02,
        seller_fee_rate=0.05,
        return_risk=0.03,
        reputation_risk=0.02,
        payment_success=payment_success,
        failure_reason=None if payment_success else "card_declined",
    )


def test_fixture_transaction_simulator_computes_costs():
    outcome = make_transaction_simulator().settle(
        TransactionRequest(
            scenario=make_scenario(),
            negotiated_price=760.0,
            accepting_role="seller",
        )
    )

    assert outcome.status == "completed"
    assert outcome.buyer_total_cost == 858.0
    assert outcome.seller_net_revenue == 718.0
    assert outcome.risk_exposure == 0.05


def test_fixture_transaction_simulator_includes_dispute_risk():
    simulator = FixtureTransactionSimulator(
        return_risk=0.03,
        reputation_risk=0.02,
        dispute_risk=0.04,
    )

    outcome = simulator.settle(
        TransactionRequest(
            scenario=make_scenario(),
            negotiated_price=760.0,
            accepting_role="seller",
        )
    )

    assert outcome.status == "completed"
    assert outcome.dispute_risk == 0.04
    assert outcome.risk_exposure == 0.09
    assert outcome.metadata["computed_risk_exposure"] == 0.09
    assert outcome.metadata["lifecycle_stage"] == "completed"


def test_fixture_transaction_simulator_records_structured_lifecycle_terms():
    simulator = FixtureTransactionSimulator(
        shipping_cost=18.0,
        escrow_fee=4.0,
        payment_method="card",
        payment_processor="fixture_gateway",
        escrow_release_policy="release_on_delivery",
        shipping_carrier="fixture_carrier",
        shipping_service="ground",
        tracking_required=True,
        delivery_days=4,
        max_delivery_days=7,
        return_window_days=14,
        min_return_window_days=7,
        return_shipping_payer="buyer",
        inspection_period_days=2,
        warranty_days=30,
        min_warranty_days=14,
        warranty_provider="seller",
        compliance_checks=("serial_verified", "not_recalled"),
        compliance_passed=True,
        dispute_window_days=30,
        dispute_resolution_policy="platform_mediation",
        dispute_risk=0.04,
    )

    outcome = simulator.settle(
        TransactionRequest(
            scenario=make_scenario(),
            negotiated_price=760.0,
            accepting_role="seller",
        )
    )

    terms = outcome.metadata["transaction_terms"]
    assert outcome.status == "completed"
    assert terms["schema_version"] == "opennego.transaction_terms.v1"
    assert terms["payment"]["method"] == "card"
    assert terms["payment"]["escrow_release_policy"] == "release_on_delivery"
    assert terms["logistics"]["carrier"] == "fixture_carrier"
    assert terms["logistics"]["tracking_required"] is True
    assert terms["returns"]["return_shipping_payer"] == "buyer"
    assert terms["warranty"]["warranty_days"] == 30
    assert terms["compliance"]["checks"] == ["serial_verified", "not_recalled"]
    assert terms["compliance"]["passed"] is True
    assert terms["dispute"]["resolution_policy"] == "platform_mediation"


@pytest.mark.parametrize(
    ("kwargs", "reason", "guard", "stage"),
    [
        (
            {"shipping_success": False},
            "shipping_failed",
            "shipping_success",
            "shipping",
        ),
        (
            {"item_matches_listing": False},
            "item_mismatch_dispute",
            "item_matches_listing",
            "dispute",
        ),
        (
            {"return_window_days": 7, "min_return_window_days": 14},
            "return_window_below_minimum",
            "min_return_window_days",
            "returns",
        ),
        (
            {"dispute_risk": 0.12, "max_dispute_risk": 0.08},
            "dispute_risk_exceeded",
            "max_dispute_risk",
            "dispute",
        ),
        (
            {"delivery_days": 9, "max_delivery_days": 5},
            "delivery_sla_exceeded",
            "max_delivery_days",
            "logistics",
        ),
        (
            {"warranty_days": 7, "min_warranty_days": 30},
            "warranty_below_minimum",
            "min_warranty_days",
            "warranty",
        ),
        (
            {"compliance_checks": ("serial_verified",), "compliance_passed": False},
            "compliance_check_failed",
            "compliance_passed",
            "compliance",
        ),
    ],
)
def test_fixture_transaction_simulator_lifecycle_failures(
    kwargs,
    reason,
    guard,
    stage,
):
    simulator = FixtureTransactionSimulator(**kwargs)

    outcome = simulator.settle(
        TransactionRequest(
            scenario=make_scenario(),
            negotiated_price=760.0,
            accepting_role="seller",
        )
    )

    assert outcome.status == "failed"
    assert outcome.failure_reason == reason
    assert outcome.metadata["violated_guard"] == guard
    assert outcome.metadata["lifecycle_stage"] == stage
    assert outcome.metadata["computed_buyer_total_cost"] == 760.0
    assert outcome.metadata["computed_seller_net_revenue"] == 760.0
    assert outcome.metadata["transaction_terms"]["schema_version"] == (
        "opennego.transaction_terms.v1"
    )


def test_fixture_transaction_simulator_fails_buyer_total_cap():
    simulator = FixtureTransactionSimulator(
        shipping_cost=18.0,
        tax_rate=0.08,
        escrow_fee=4.0,
        payment_fee_rate=0.02,
        seller_fee_rate=0.05,
        max_buyer_total_cost=850.0,
    )

    outcome = simulator.settle(
        TransactionRequest(
            scenario=make_scenario(),
            negotiated_price=760.0,
            accepting_role="seller",
        )
    )

    assert outcome.status == "failed"
    assert outcome.failure_reason == "buyer_total_cost_exceeded"
    assert outcome.buyer_total_cost == 0.0
    assert outcome.metadata["computed_buyer_total_cost"] == 858.0
    assert outcome.metadata["computed_seller_net_revenue"] == 718.0
    assert outcome.metadata["max_buyer_total_cost"] == 850.0
    assert outcome.metadata["violated_guard"] == "max_buyer_total_cost"


def test_fixture_transaction_simulator_fails_seller_net_floor():
    simulator = FixtureTransactionSimulator(
        shipping_cost=18.0,
        tax_rate=0.08,
        escrow_fee=4.0,
        payment_fee_rate=0.02,
        seller_fee_rate=0.05,
        min_seller_net_revenue=720.0,
    )

    outcome = simulator.settle(
        TransactionRequest(
            scenario=make_scenario(),
            negotiated_price=760.0,
            accepting_role="seller",
        )
    )

    assert outcome.status == "failed"
    assert outcome.failure_reason == "seller_net_revenue_below_floor"
    assert outcome.seller_net_revenue == 0.0
    assert outcome.metadata["computed_buyer_total_cost"] == 858.0
    assert outcome.metadata["computed_seller_net_revenue"] == 718.0
    assert outcome.metadata["min_seller_net_revenue"] == 720.0
    assert outcome.metadata["violated_guard"] == "min_seller_net_revenue"


def test_scripted_deal_appends_transaction_event_and_metrics():
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(make_market_tool(),),
        transaction_simulator=make_transaction_simulator(),
    )

    result = env.run()

    assert result.outcome == "deal"
    assert result.deal_price == 760.0
    assert result.transaction is not None
    assert result.transaction.status == "completed"
    assert result.events[-1].action_type == ActionType.TRANSACTION
    assert result.events[-1].actor == "transaction_simulator"
    assert result.metrics["buyer_total_transaction_cost"] == 858.0
    assert result.metrics["seller_net_transaction_revenue"] == 718.0
    assert result.metrics["transaction_completed_rate"] == 1.0
    assert result.metrics["failed_transaction_rate"] == 0.0


def test_failed_transaction_is_distinct_from_negotiated_deal():
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(make_market_tool(),),
        transaction_simulator=make_transaction_simulator(payment_success=False),
    )

    result = env.run()

    assert result.outcome == "deal"
    assert result.deal_price == 760.0
    assert result.transaction is not None
    assert result.transaction.status == "failed"
    assert result.transaction.failure_reason == "card_declined"
    assert result.metrics["failed_transaction_rate"] == 1.0
    assert result.metrics["buyer_total_transaction_cost"] == 0.0
    assert result.metrics["seller_net_transaction_revenue"] == 0.0
    assert result.transaction.metadata["computed_buyer_total_cost"] == 858.0
    assert result.transaction.metadata["computed_seller_net_revenue"] == 718.0


def test_transaction_artifacts_round_trip(tmp_path):
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(make_market_tool(),),
        transaction_simulator=FixtureTransactionSimulator(dispute_risk=0.04),
    )
    result = env.run()

    from opennego.artifacts import write_run_artifacts

    paths = write_run_artifacts(
        result=result,
        output_dir=tmp_path,
        run_id="transaction-smoke",
    )

    trace = load_trace(paths.trace_path)
    metrics = load_metric_report(paths.metrics_path)

    assert trace[-1].action_type == ActionType.TRANSACTION
    assert trace[-1].transaction is not None
    assert trace[-1].transaction.buyer_total_cost == 760.0
    assert trace[-1].transaction.dispute_risk == 0.04
    assert metrics.metrics["seller_net_transaction_revenue"] == 760.0
    assert metrics.metrics["transaction_dispute_risk"] == 0.04


def test_runner_transaction_guard_config_records_failed_settlement(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = tmp_path / "transaction_guard.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "opennego.experiment.v1",
                "name": "transaction_guard",
                "output_dir": str(output_dir),
                "resume": False,
                "fail_fast": True,
                "seeds": [5],
                "agents": {
                    "buyer": {"kind": "tool_aware_buyer"},
                    "seller": {"kind": "scripted_seller"},
                },
                "transaction": {
                    "kind": "fixture",
                    "enabled": True,
                    "shipping_cost": 18.0,
                    "tax_rate": 0.08,
                    "escrow_fee": 4.0,
                    "payment_fee_rate": 0.02,
                    "seller_fee_rate": 0.05,
                    "max_buyer_total_cost": 850.0,
                    "min_seller_net_revenue": 700.0,
                },
                "scenarios": [
                    {
                        "id": "camera_001",
                        "products_file": "examples/data/products.json",
                        "product_index": 0,
                        "max_turns": 8,
                    }
                ],
                "tool_regimes": [
                    {
                        "id": "buyer_private_market_search",
                        "tools": [
                            {
                                "name": "market_price_search",
                                "kind": "market_price",
                                "source": "examples/data/market_comps.json",
                                "visibility": "buyer_private",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    summary = run_experiment_config(config_path)
    run_dir = (
        output_dir
        / "transaction_guard-camera_001-buyer_private_market_search-seed-5"
    )
    manifest = load_manifest(run_dir / "manifest.json")
    trace = load_trace(run_dir / "trace.jsonl")
    metrics = load_metric_report(run_dir / "metrics.json")

    assert summary.completed == 1
    assert manifest.metadata["transaction"]["max_buyer_total_cost"] == 850.0
    assert manifest.metadata["transaction"]["min_seller_net_revenue"] == 700.0
    assert trace[-1].transaction is not None
    assert trace[-1].transaction.status == "failed"
    assert trace[-1].transaction.failure_reason == "buyer_total_cost_exceeded"
    assert trace[-1].transaction.metadata["computed_buyer_total_cost"] == 858.0
    assert metrics.metrics["failed_transaction_rate"] == 1.0


def test_runner_transaction_lifecycle_config_records_dispute_failure(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = tmp_path / "transaction_lifecycle.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "opennego.experiment.v1",
                "name": "transaction_lifecycle",
                "output_dir": str(output_dir),
                "resume": False,
                "fail_fast": True,
                "seeds": [5],
                "agents": {
                    "buyer": {"kind": "tool_aware_buyer"},
                    "seller": {"kind": "scripted_seller"},
                },
                "transaction": {
                    "kind": "fixture",
                    "enabled": True,
                    "dispute_risk": 0.12,
                    "max_dispute_risk": 0.08,
                    "return_window_days": 7,
                    "min_return_window_days": 3,
                    "shipping_success": True,
                    "item_matches_listing": True,
                },
                "scenarios": [
                    {
                        "id": "camera_001",
                        "products_file": "examples/data/products.json",
                        "product_index": 0,
                        "max_turns": 8,
                    }
                ],
                "tool_regimes": [
                    {
                        "id": "buyer_private_market_search",
                        "tools": [
                            {
                                "name": "market_price_search",
                                "kind": "market_price",
                                "source": "examples/data/market_comps.json",
                                "visibility": "buyer_private",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    summary = run_experiment_config(config_path)
    run_dir = (
        output_dir
        / "transaction_lifecycle-camera_001-buyer_private_market_search-seed-5"
    )
    manifest = load_manifest(run_dir / "manifest.json")
    trace = load_trace(run_dir / "trace.jsonl")
    metrics = load_metric_report(run_dir / "metrics.json")

    assert summary.completed == 1
    assert manifest.metadata["transaction"]["dispute_risk"] == 0.12
    assert manifest.metadata["transaction"]["max_dispute_risk"] == 0.08
    assert manifest.metadata["transaction"]["return_window_days"] == 7
    assert manifest.metadata["transaction"]["min_return_window_days"] == 3
    assert trace[-1].transaction is not None
    assert trace[-1].transaction.status == "failed"
    assert trace[-1].transaction.failure_reason == "dispute_risk_exceeded"
    assert trace[-1].transaction.dispute_risk == 0.12
    assert trace[-1].transaction.metadata["violated_guard"] == "max_dispute_risk"
    assert metrics.metrics["failed_transaction_rate"] == 1.0
    assert metrics.metrics["transaction_dispute_risk"] == 0.12


def test_runner_transaction_terms_config_records_completed_lifecycle(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = tmp_path / "transaction_terms.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "opennego.experiment.v1",
                "name": "transaction_terms",
                "output_dir": str(output_dir),
                "resume": False,
                "fail_fast": True,
                "seeds": [5],
                "agents": {
                    "buyer": {"kind": "tool_aware_buyer"},
                    "seller": {"kind": "scripted_seller"},
                },
                "transaction": {
                    "kind": "fixture",
                    "enabled": True,
                    "shipping_cost": 18.0,
                    "tax_rate": 0.08,
                    "escrow_fee": 4.0,
                    "payment_fee_rate": 0.02,
                    "seller_fee_rate": 0.05,
                    "payment_method": "card",
                    "payment_processor": "fixture_gateway",
                    "escrow_release_policy": "release_on_delivery",
                    "shipping_carrier": "fixture_carrier",
                    "shipping_service": "insured_ground",
                    "tracking_required": True,
                    "delivery_days": 4,
                    "max_delivery_days": 7,
                    "return_window_days": 14,
                    "min_return_window_days": 7,
                    "return_shipping_payer": "buyer",
                    "inspection_period_days": 2,
                    "warranty_days": 30,
                    "min_warranty_days": 14,
                    "warranty_provider": "seller",
                    "compliance_checks": ["serial_verified", "not_recalled"],
                    "compliance_passed": True,
                    "dispute_window_days": 30,
                    "dispute_resolution_policy": "platform_mediation",
                },
                "scenarios": [
                    {
                        "id": "camera_001",
                        "products_file": "examples/data/products.json",
                        "product_index": 0,
                        "max_turns": 8,
                    }
                ],
                "tool_regimes": [
                    {
                        "id": "buyer_private_market_search",
                        "tools": [
                            {
                                "name": "market_price_search",
                                "kind": "market_price",
                                "source": "examples/data/market_comps.json",
                                "visibility": "buyer_private",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    summary = run_experiment_config(config_path)
    run_dir = output_dir / (
        "transaction_terms-camera_001-buyer_private_market_search-seed-5"
    )
    manifest = load_manifest(run_dir / "manifest.json")
    trace = load_trace(run_dir / "trace.jsonl")

    assert summary.completed == 1
    assert manifest.metadata["transaction"]["payment_method"] == "card"
    assert manifest.metadata["transaction"]["shipping_service"] == "insured_ground"
    assert manifest.metadata["transaction"]["compliance_checks"] == [
        "serial_verified",
        "not_recalled",
    ]
    assert trace[-1].transaction is not None
    assert trace[-1].transaction.status == "completed"
    terms = trace[-1].transaction.metadata["transaction_terms"]
    assert terms["payment"]["processor"] == "fixture_gateway"
    assert terms["logistics"]["max_delivery_days"] == 7
    assert terms["warranty"]["provider"] == "seller"
    assert terms["dispute"]["window_days"] == 30
