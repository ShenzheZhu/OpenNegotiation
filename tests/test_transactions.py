from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import load_metric_report, load_trace
from opennego.environment import NegotiationEnvironment
from opennego.ports import TransactionRequest
from opennego.schema import ActionType, Product, Scenario
from opennego.tools import MarketComparable, MarketPriceTool
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


def test_transaction_artifacts_round_trip(tmp_path):
    env = NegotiationEnvironment(
        scenario=make_scenario(),
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(make_market_tool(),),
        transaction_simulator=make_transaction_simulator(),
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
    assert trace[-1].transaction.buyer_total_cost == 858.0
    assert metrics.metrics["seller_net_transaction_revenue"] == 718.0
