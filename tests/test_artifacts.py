import json
from pathlib import Path

import pytest

from opennego.artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactValidationError,
    ScenarioArtifact,
    load_manifest,
    load_metric_report,
    load_scenario_artifact,
    load_trace,
    recompute_metrics_from_artifacts,
    write_run_artifacts,
)
from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.environment import NegotiationEnvironment
from opennego.schema import Product, Scenario
from opennego.tools import MarketComparable, MarketPriceTool


def make_result():
    product = Product(
        id="camera_001",
        name="Sony Alpha a6400 Mirrorless Camera Body",
        description="Used mirrorless camera body.",
        condition="used",
        list_price=1000.0,
        wholesale_price=620.0,
    )
    scenario = Scenario(
        product=product,
        buyer_budget=850.0,
        seller_reservation_price=620.0,
        max_turns=6,
    )
    tool = MarketPriceTool(
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
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(tool,),
    )
    return env.run()


def test_write_and_load_versioned_run_artifacts(tmp_path):
    result = make_result()

    paths = write_run_artifacts(
        result=result,
        output_dir=tmp_path,
        run_id="golden-smoke-camera_001",
        agents={
            "buyer": {"name": "tool_aware_buyer", "kind": "scripted"},
            "seller": {"name": "scripted_seller", "kind": "scripted"},
        },
        tool_regime={"market_price_search": {"visibility": "buyer_private"}},
    )

    manifest = load_manifest(paths.manifest_path)
    scenario = load_scenario_artifact(paths.scenario_path)
    trace = load_trace(paths.trace_path)
    metrics = load_metric_report(paths.metrics_path)

    assert manifest.schema_version == ARTIFACT_SCHEMA_VERSION
    assert manifest.run_id == "golden-smoke-camera_001"
    assert scenario.scenario_id == "camera_001"
    assert len(trace) == 3
    assert trace[0].private is True
    assert trace[0].tool_result["median_price"] == 800.0
    assert metrics.outcome == "deal"
    assert metrics.deal_price == 760.0
    assert recompute_metrics_from_artifacts(scenario, trace) == metrics.metrics


def test_trace_matches_golden_fixture(tmp_path):
    result = make_result()

    paths = write_run_artifacts(
        result=result,
        output_dir=tmp_path,
        run_id="golden-smoke-camera_001",
        agents={
            "buyer": {"name": "tool_aware_buyer", "kind": "scripted"},
            "seller": {"name": "scripted_seller", "kind": "scripted"},
        },
        tool_regime={"market_price_search": {"visibility": "buyer_private"}},
    )

    actual = [json.loads(line) for line in paths.trace_path.read_text().splitlines()]
    expected_path = Path(__file__).parent / "fixtures" / "golden_trace.jsonl"
    expected = [json.loads(line) for line in expected_path.read_text().splitlines()]

    assert actual == expected


def test_scenario_artifact_rejects_malformed_schema_version():
    with pytest.raises(ArtifactValidationError, match="schema_version"):
        ScenarioArtifact.from_mapping({"schema_version": "bad"})


def test_scenario_artifact_rejects_malformed_product_with_contract_error():
    with pytest.raises(ArtifactValidationError, match="product"):
        ScenarioArtifact.from_mapping(
            {
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "scenario_id": "bad",
                "product": {},
                "buyer_budget": 1,
                "seller_reservation_price": 1,
                "max_turns": 1,
            }
        )
