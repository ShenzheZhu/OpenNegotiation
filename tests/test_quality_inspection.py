import json
from dataclasses import dataclass, field

import pytest

from opennego.agents import ScriptedSeller
from opennego.artifacts import (
    ArtifactValidationError,
    ScenarioArtifact,
    to_jsonable,
    write_run_artifacts,
)
from opennego.coaching import build_coach_case
from opennego.environment import NegotiationEnvironment, ToolRuntimeConfig
from opennego.quality import DEFAULT_QUALITY, condition_to_quality
from opennego.schema import (
    ActionType,
    AgentAction,
    AgentContext,
    Product,
    Role,
    Scenario,
)
from opennego.tools import QualityInspectionTool


def _product(condition: str = "Used - Like New") -> Product:
    return Product(
        id="phone_001",
        name="Apple iPhone 13 128GB",
        description="Unlocked smartphone.",
        condition=condition,
        list_price=600.0,
        wholesale_price=300.0,
    )


def _scenario(**kwargs) -> Scenario:
    return Scenario(
        product=_product(kwargs.pop("condition", "Used - Like New")),
        buyer_budget=550.0,
        seller_reservation_price=320.0,
        max_turns=6,
        **kwargs,
    )


@dataclass
class _SequenceBuyer:
    name: str = "buyer"
    role: Role = Role.BUYER
    actions: list = field(default_factory=list)

    def act(self, context: AgentContext) -> AgentAction:
        if self.actions:
            return self.actions.pop(0)
        return AgentAction.reject("done")


# --- condition_to_quality mapping -----------------------------------------


@pytest.mark.parametrize(
    "condition,expected",
    [
        ("Brand New", 1.0),
        ("New (Other)", 0.95),
        ("Used - Like New", 0.9),
        ("Used - Very Good", 0.72),
        ("Used - Good", 0.6),
        ("Used - Acceptable", 0.45),
        ("For parts or not working", 0.15),
        ("Certified Refurbished", 0.88),
        ("Seller Refurbished", 0.8),
        ("Renewed", 0.8),  # contains the substring "new" but must resolve refurbished
        ("", DEFAULT_QUALITY),
        ("mystery condition", DEFAULT_QUALITY),
    ],
)
def test_condition_to_quality_bands(condition, expected):
    assert condition_to_quality(condition) == expected


def test_condition_to_quality_handles_none():
    assert condition_to_quality(None) == DEFAULT_QUALITY


# --- schema field ----------------------------------------------------------


def test_seller_true_quality_defaults_none_and_validates_range():
    assert _scenario().seller_true_quality is None
    _scenario(seller_true_quality=0.0)  # bounds are inclusive
    _scenario(seller_true_quality=1.0)
    with pytest.raises(ValueError):
        _scenario(seller_true_quality=1.5)
    with pytest.raises(ValueError):
        _scenario(seller_true_quality=-0.1)


# --- environment private routing ------------------------------------------


def test_seller_sees_true_quality_buyer_does_not():
    scenario = _scenario(seller_true_quality=0.4)
    env = NegotiationEnvironment(
        scenario=scenario, buyer=_SequenceBuyer(), seller=ScriptedSeller()
    )
    seller_state = env._context_for(Role.SELLER).private_state
    buyer_state = env._context_for(Role.BUYER).private_state
    assert seller_state["true_quality"] == 0.4
    assert "true_quality" not in buyer_state


def test_true_quality_absent_is_additive():
    env = NegotiationEnvironment(
        scenario=_scenario(), buyer=_SequenceBuyer(), seller=ScriptedSeller()
    )
    assert "true_quality" not in env._context_for(Role.SELLER).private_state


# --- artifact round-trip ---------------------------------------------------


def test_scenario_artifact_round_trips_true_quality():
    scenario = _scenario(seller_true_quality=0.37)
    artifact = ScenarioArtifact.from_scenario(scenario, scenario_id="s1")
    restored = ScenarioArtifact.from_mapping(json.loads(json.dumps(to_jsonable(artifact))))
    assert restored.seller_true_quality == 0.37
    assert restored.to_scenario().seller_true_quality == 0.37


def test_scenario_artifact_rejects_out_of_range_true_quality():
    artifact = ScenarioArtifact.from_scenario(
        _scenario(seller_true_quality=0.4), scenario_id="s1"
    )
    payload = json.loads(json.dumps(to_jsonable(artifact)))
    payload["seller_true_quality"] = 2.0
    with pytest.raises(ArtifactValidationError):
        ScenarioArtifact.from_mapping(payload)


# --- coach red line --------------------------------------------------------


def test_coach_case_red_line_excludes_true_quality_for_buyer(tmp_path):
    scenario = _scenario(seller_true_quality=0.33)
    env = NegotiationEnvironment(
        scenario=scenario, buyer=_SequenceBuyer(), seller=ScriptedSeller()
    )
    result = env.run()
    paths = write_run_artifacts(
        result=result,
        output_dir=tmp_path,
        run_id="quality-run",
        agents={
            "buyer": {"name": "buyer", "kind": "scripted"},
            "seller": {"name": "scripted_seller", "kind": "scripted"},
        },
        tool_regime={},
    )
    buyer_case = build_coach_case(paths.output_dir, user_role=Role.BUYER)
    seller_case = build_coach_case(paths.output_dir, user_role=Role.SELLER)
    assert "true_quality" not in buyer_case.user_private
    assert seller_case.user_private["true_quality"] == 0.33


# --- inspect tool ----------------------------------------------------------


def test_inspect_estimate_is_deterministic_and_in_band():
    scenario = _scenario(seller_true_quality=0.4)
    tool_a = QualityInspectionTool.from_scenario(scenario, base_seed=7)
    tool_b = QualityInspectionTool.from_scenario(scenario, base_seed=7)
    result_a = tool_a.call({}, None)
    result_b = tool_b.call({}, None)
    assert result_a == result_b
    # Single noisy sample stays within +/- noise_std of the truth.
    assert 0.4 - result_a["noise_std"] <= result_a["estimate_quality"] <= 0.4 + result_a["noise_std"]
    # The raw truth is never echoed back to the caller.
    assert "true_quality" not in result_a


def test_inspect_repeats_tighten_interval_and_track_claim_gap():
    scenario = _scenario(seller_true_quality=0.4)  # claim "Like New" -> 0.9
    tool = QualityInspectionTool.from_scenario(scenario, base_seed=3)
    first = tool.call({}, None)
    for _ in range(8):
        latest = tool.call({}, None)
    # Confidence band shrinks as samples accumulate.
    first_width = first["estimate_high"] - first["estimate_low"]
    latest_width = latest["estimate_high"] - latest["estimate_low"]
    assert latest["samples_taken"] == 9
    assert latest_width < first_width
    # Claim is 0.9, truth is 0.4 -> the item looks materially worse than claimed.
    assert latest["claimed_quality"] == 0.9
    assert latest["below_claim"] > 0.2
    # The running estimate converges toward the truth.
    assert abs(latest["estimate_quality"] - 0.4) < 0.05


def test_inspect_without_hidden_quality_centers_on_claim():
    scenario = _scenario(condition="Used - Very Good")  # no hidden defect -> 0.72
    tool = QualityInspectionTool.from_scenario(scenario, base_seed=1)
    result = tool.call({}, None)
    assert result["claimed_quality"] == 0.72
    assert abs(result["below_claim"]) <= result["noise_std"]


def test_inspect_through_environment_is_buyer_private():
    scenario = _scenario(seller_true_quality=0.4)
    buyer = _SequenceBuyer(
        actions=[AgentAction.tool("inspect", {}), AgentAction.offer_price(400, "offer")]
    )
    env = NegotiationEnvironment(
        scenario=scenario,
        buyer=buyer,
        seller=ScriptedSeller(),
        tools=(QualityInspectionTool.from_scenario(scenario, base_seed=5),),
        tool_configs=(
            ToolRuntimeConfig(name="inspect", roles=(Role.BUYER,), visibility="private"),
        ),
    )
    result = env.run()
    tool_event = result.events[0]
    assert tool_event.action_type == ActionType.TOOL_CALL
    assert tool_event.private is True
    assert tool_event.tool_result["ok"] is True
    assert "estimate_quality" in tool_event.tool_result
    # Even the tool the buyer calls never names the raw truth key.
    assert "true_quality" not in tool_event.tool_result
    # ...and the buyer's own context still never carries it.
    assert "true_quality" not in env._context_for(Role.BUYER).private_state
