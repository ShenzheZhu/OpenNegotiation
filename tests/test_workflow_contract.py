import json
from pathlib import Path

from opennego.artifacts import (
    load_manifest,
    load_metric_report,
    load_scenario_artifact,
    load_trace,
)
from opennego.evolution import (
    STRATEGY_COMPARISON_SCHEMA_VERSION,
    STRATEGY_EVOLUTION_SCHEMA_VERSION,
    write_strategy_candidate,
    write_strategy_comparison,
)
from opennego.learning import (
    POLICY_LEARNING_SCHEMA_VERSION,
    load_strategy_registry,
    write_battle_report,
)
from opennego.marketplace import (
    MARKETPLACE_PROFILE_SCHEMA_VERSION,
    load_marketplace_profile,
    write_marketplace_profile,
)
from opennego.runner import run_experiment_config
from opennego.sparring import (
    SPARRING_EXECUTION_MODE,
    SPARRING_SUITE_SCHEMA_VERSION,
    run_sparring_suite,
)


def test_user_centric_workflow_contract_round_trips_artifacts(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    benchmark = run_experiment_config(
        "configs/real_market_demo.yaml",
        output_dir=benchmark_dir,
    )
    before_run = _run_by_tool_regime(benchmark.runs, "no_tools")
    market_tool_run = _run_by_tool_regime(
        benchmark.runs,
        "buyer_private_market_search",
    )

    assert benchmark.completed == 3
    assert benchmark.failed == 0
    _assert_run_artifacts(
        before_run.output_dir,
        expected_buyer_kind="tool_aware_buyer",
        expected_seller_kind="scripted_seller",
        expected_experiment="real_market_demo",
    )
    _assert_run_artifacts(
        market_tool_run.output_dir,
        expected_buyer_kind="tool_aware_buyer",
        expected_seller_kind="scripted_seller",
        expected_experiment="real_market_demo",
    )

    before_report = tmp_path / "before_battle_report.json"
    market_tool_report = tmp_path / "market_tool_battle_report.json"
    write_battle_report(
        before_run.output_dir,
        before_report,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    write_battle_report(
        market_tool_run.output_dir,
        market_tool_report,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    before_payload = json.loads(before_report.read_text())
    market_tool_payload = json.loads(market_tool_report.read_text())

    assert before_payload["schema_version"] == POLICY_LEARNING_SCHEMA_VERSION
    assert before_payload["user_role"] == "buyer"
    assert before_payload["opponent_profile_id"] == "seller_hardline_anchor_v1"
    assert "buyer_overpaid_market" in {
        lesson["id"] for lesson in before_payload["lessons"]
    }
    assert market_tool_payload["schema_version"] == POLICY_LEARNING_SCHEMA_VERSION
    assert market_tool_payload["user_role"] == before_payload["user_role"]

    candidate_path = tmp_path / "strategy_candidate.json"
    write_strategy_candidate(
        before_report,
        candidate_path,
        parent_strategy_id="buyer_baseline",
        iteration=1,
    )
    candidate = json.loads(candidate_path.read_text())

    assert candidate["schema_version"] == STRATEGY_EVOLUTION_SCHEMA_VERSION
    assert candidate["candidate_id"] == "buyer_baseline-iter-1"
    assert candidate["user_role"] == "buyer"
    assert candidate["metadata"]["base_prompt_fixed"] is True
    assert "buyer_overpaid_market" in candidate["applied_lesson_ids"]

    sparring_dir = tmp_path / "sparring"
    sparring = run_sparring_suite(
        output_dir=sparring_dir,
        opponent_profile_ids=("seller_hardline_anchor_v1",),
        user_strategy_path=candidate_path,
    )
    sparring_payload = json.loads((sparring_dir / "sparring_suite.json").read_text())
    sparring_result = sparring.results[0]
    sparring_manifest = load_manifest(
        Path(sparring_result.learning_input_dir) / "manifest.json"
    )

    assert sparring.schema_version == SPARRING_SUITE_SCHEMA_VERSION
    assert sparring.execution_mode == SPARRING_EXECUTION_MODE
    assert sparring.completed == 1
    assert sparring.failed == 0
    assert sparring_payload["user_strategy_candidate_id"] == "buyer_baseline-iter-1"
    assert sparring_result.user_strategy_candidate_id == "buyer_baseline-iter-1"
    assert sparring_result.profile_id == "seller_hardline_anchor_v1"
    assert sparring_manifest.metadata["sparring_execution_mode"] == (
        SPARRING_EXECUTION_MODE
    )
    assert sparring_manifest.metadata["user_strategy"]["enabled"] is True
    assert sparring_manifest.agents["buyer"]["kind"] == "strategy_candidate_buyer"
    assert sparring_manifest.agents["buyer"]["candidate_id"] == (
        "buyer_baseline-iter-1"
    )
    assert sparring_manifest.agents["seller"]["profile_id"] == (
        "seller_hardline_anchor_v1"
    )
    _assert_run_artifacts(
        sparring_result.learning_input_dir,
        expected_buyer_kind="strategy_candidate_buyer",
        expected_seller_kind="strategy_profile_seller",
        expected_experiment="real_market_demo",
    )

    after_report = Path(sparring_result.battle_report)
    comparison_path = tmp_path / "comparison.json"
    write_strategy_comparison(before_report, after_report, comparison_path)
    comparison = json.loads(comparison_path.read_text())

    assert comparison["schema_version"] == STRATEGY_COMPARISON_SCHEMA_VERSION
    assert comparison["before_battle_report"] == str(before_report)
    assert comparison["after_battle_report"] == str(after_report)
    assert comparison["user_role"] == "buyer"
    assert comparison["metadata"]["before_opponent_profile_id"] == (
        "seller_hardline_anchor_v1"
    )
    assert comparison["metadata"]["after_opponent_profile_id"] == (
        "seller_hardline_anchor_v1"
    )

    profile_path = tmp_path / "marketplace_profile.json"
    registry_path = tmp_path / "strategy_registry.json"
    export = write_marketplace_profile(
        candidate_path,
        profile_path,
        profile_id="buyer_market_guard_v1",
        name="Buyer Market Guard",
        tags=("workflow",),
        allowed_tools=("market_price_search",),
        install_registry_path=registry_path,
    )
    profile = load_marketplace_profile(profile_path)
    registry = load_strategy_registry(registry_path)
    registry_profile = registry.by_id("buyer_market_guard_v1")
    marketplace_payload = json.loads(profile_path.read_text())

    assert export.profile_id == "buyer_market_guard_v1"
    assert export.installed_registry == str(registry_path)
    assert marketplace_payload["schema_version"] == MARKETPLACE_PROFILE_SCHEMA_VERSION
    assert profile.id == registry_profile.id == "buyer_market_guard_v1"
    assert registry_profile.role.value == "buyer"
    assert registry_profile.metadata["candidate_id"] == "buyer_baseline-iter-1"
    assert registry_profile.metadata["source_type"] == "strategy_candidate"


def _run_by_tool_regime(records, tool_regime):
    for record in records:
        if record.status == "completed" and f"-{tool_regime}-" in record.run_id:
            return record
    raise AssertionError(f"missing completed run for tool regime {tool_regime!r}")


def _assert_run_artifacts(
    run_dir,
    *,
    expected_buyer_kind,
    expected_seller_kind,
    expected_experiment,
):
    run_path = Path(run_dir)
    manifest = load_manifest(run_path / "manifest.json")
    scenario = load_scenario_artifact(run_path / "scenario.json")
    trace = load_trace(run_path / "trace.jsonl")
    metrics = load_metric_report(run_path / "metrics.json")

    assert manifest.run_id == metrics.run_id
    assert manifest.scenario_id == scenario.scenario_id == metrics.scenario_id
    assert manifest.metadata["experiment_name"] == expected_experiment
    assert manifest.agents["buyer"]["kind"] == expected_buyer_kind
    assert manifest.agents["seller"]["kind"] == expected_seller_kind
    assert scenario.product.market_reference is not None
    assert trace
    assert all(record.run_id == manifest.run_id for record in trace)
    assert metrics.metrics["market_price_gap"] >= 0.0
    assert metrics.metrics["normalized_market_gap"] >= 0.0
