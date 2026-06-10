import json

import pytest

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import to_jsonable, write_run_artifacts
from opennego.coaching import (
    BATTLE_REPORT_V2_SCHEMA_VERSION,
    BattleReport,
    BattleReportValidationError,
    CoachCase,
    DecisionPoint,
    Lesson,
    OutcomeSummary,
    SafetyVerdict,
    Weakness,
    build_coach_case,
    public_opponent_card,
    validate_battle_report,
)
from opennego.environment import NegotiationEnvironment, ToolRuntimeConfig
from opennego.learning import load_strategy_registry
from opennego.ports import CoachPort
from opennego.scenario_generator import generate_scenarios, load_products
from opennego.schema import Role
from opennego.tools import MarketPriceTool


def _write_run(tmp_path, opponent_profile_id=None):
    scenario = generate_scenarios(
        load_products("examples/data/real_market_products.json"), seed=13
    )[0]
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
        tools=(MarketPriceTool.from_json("examples/data/real_market_comps.json"),),
        tool_configs=(
            ToolRuntimeConfig(
                name="market_price_search",
                roles=(Role.BUYER,),
                visibility="private",
            ),
        ),
    )
    result = env.run()
    metadata = {}
    if opponent_profile_id:
        metadata["opponent_profile_id"] = opponent_profile_id
    paths = write_run_artifacts(
        result=result,
        output_dir=tmp_path,
        run_id="coach-case-run",
        agents={
            "buyer": {"name": "tool_aware_buyer", "kind": "scripted"},
            "seller": {"name": "scripted_seller", "kind": "scripted"},
        },
        tool_regime={"market_price_search": {"visibility": "buyer_private"}},
        metadata=metadata,
    )
    return paths.output_dir


def _sample_report(run_id="coach-case-run", user_role=Role.BUYER, turn=1):
    return BattleReport(
        schema_version=BATTLE_REPORT_V2_SCHEMA_VERSION,
        run_id=run_id,
        user_role=user_role,
        coach={"kind": "rules"},
        outcome_summary=OutcomeSummary(outcome="deal", deal_price=612.5),
        decision_points=(
            DecisionPoint(
                turn=turn,
                phase="negotiation",
                situation="seller anchored high",
                action_taken="countered at retrieved median",
                assessment="good_use_of_evidence",
            ),
        ),
        weaknesses=(
            Weakness(
                id="buyer_overpaid_market",
                phase="negotiation",
                severity="major",
                summary="accepted above reference",
                evidence_turns=(turn,),
            ),
        ),
        lessons=(Lesson(id="buyer_overpaid_market", patch="Anchor on comps."),),
    )


def test_battle_report_round_trips_through_json():
    report = _sample_report()

    payload = json.loads(json.dumps(to_jsonable(report)))
    restored = BattleReport.from_mapping(payload)

    assert restored == report


def test_schema_rejects_unknown_phase_and_severity():
    with pytest.raises(BattleReportValidationError, match="phase"):
        DecisionPoint(
            turn=1,
            phase="vibes",
            situation="",
            action_taken="",
            assessment="",
        )
    with pytest.raises(BattleReportValidationError, match="severity"):
        Weakness(id="x", phase="closing", severity="catastrophic", summary="")


def test_from_mapping_rejects_wrong_schema_version():
    payload = to_jsonable(_sample_report())
    payload["schema_version"] = "opennego.policy_learning.v1"

    with pytest.raises(BattleReportValidationError, match="schema_version"):
        BattleReport.from_mapping(payload)


def test_buyer_case_excludes_seller_private_state(tmp_path):
    run_dir = _write_run(tmp_path)

    case = build_coach_case(run_dir, user_role=Role.BUYER)
    serialized = json.dumps(to_jsonable(case))

    assert case.user_private["budget"] > 0
    assert case.user_private["outside_option"]["basis"] == "next_best_active_listing"
    assert "seller_reservation_price" not in serialized
    assert "relist_and_wait" not in serialized
    assert "derived_reservation" not in serialized
    assert "seller_profit_vs_reservation" not in serialized
    assert "normalized_deal_price" not in serialized
    assert "batna" not in case.scenario_public["metadata"]


def test_seller_case_excludes_buyer_private_state_and_private_tools(tmp_path):
    run_dir = _write_run(tmp_path)

    case = build_coach_case(run_dir, user_role=Role.SELLER)
    serialized = json.dumps(to_jsonable(case))

    assert case.user_private["reservation_price"] > 0
    assert case.user_private["outside_option"]["basis"] == "relist_and_wait"
    assert "buyer_budget" not in serialized
    assert "buyer_budget_slack" not in serialized
    assert "next_best_active_listing" not in serialized
    assert all(
        event.action_type.value != "tool_call" for event in case.visible_trace
    )

    buyer_case = build_coach_case(run_dir, user_role=Role.BUYER)
    assert any(
        event.action_type.value == "tool_call" for event in buyer_case.visible_trace
    )


def test_opponent_card_exposes_public_fields_only(tmp_path):
    run_dir = _write_run(tmp_path, opponent_profile_id="seller_hardline_anchor_v1")

    case = build_coach_case(run_dir, user_role=Role.BUYER)

    assert case.opponent_card["archetype"] == "hardline_anchor"
    assert "strategy_prompt" not in case.opponent_card
    assert "base_prompt" not in case.opponent_card

    registry = load_strategy_registry()
    card = public_opponent_card(registry.by_id("seller_hardline_anchor_v1"))
    assert set(card) == {
        "id",
        "name",
        "archetype",
        "difficulty",
        "summary",
        "expected_traps",
        "tags",
    }


def test_validate_battle_report_grounding(tmp_path):
    run_dir = _write_run(tmp_path)
    case = build_coach_case(run_dir, user_role=Role.BUYER)
    grounded_turn = case.visible_turns[0]

    good = _sample_report(turn=grounded_turn)
    assert validate_battle_report(good, case=case) == ()

    ungrounded = _sample_report(turn=999)
    errors = validate_battle_report(ungrounded, case=case)
    assert any("not a visible turn" in error for error in errors)

    failed_safety = BattleReport(
        schema_version=BATTLE_REPORT_V2_SCHEMA_VERSION,
        run_id=case.run_id,
        user_role=Role.BUYER,
        coach={"kind": "rules"},
        outcome_summary=OutcomeSummary(outcome="deal"),
        safety=SafetyVerdict(passed=False, violations=()),
    )
    errors = validate_battle_report(failed_safety, case=case)
    assert any("safety" in error for error in errors)


def test_coach_port_protocol_accepts_minimal_implementation():
    class StubCoach:
        kind = "rules"

        def review(self, case: CoachCase) -> BattleReport:
            return _sample_report(run_id=case.run_id, user_role=case.user_role)

    assert isinstance(StubCoach(), CoachPort)
