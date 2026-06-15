import json

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import ScenarioArtifact, to_jsonable, write_run_artifacts
from opennego.coaching import build_coach_case
from opennego.environment import NegotiationEnvironment
from opennego.scenario_generator import generate_scenarios, load_products
from opennego.schema import Role, Scenario


def _scenario(**kwargs):
    product = load_products("examples/data/real_market_products.json")[0]
    return Scenario(
        product=product,
        buyer_budget=700.0,
        seller_reservation_price=520.0,
        max_turns=6,
        **kwargs,
    )


def test_true_condition_defaults_none_and_is_additive():
    scenario = _scenario()
    assert scenario.seller_true_condition is None
    env = NegotiationEnvironment(
        scenario=scenario, buyer=ToolAwareBuyer(), seller=ScriptedSeller()
    )
    # Behaves exactly as before: no true_condition in either side's state.
    assert "true_condition" not in env._context_for(Role.SELLER).private_state
    assert "true_condition" not in env._context_for(Role.BUYER).private_state


def test_seller_sees_true_condition_buyer_does_not():
    scenario = _scenario(seller_true_condition="screen has a hidden hairline crack")
    env = NegotiationEnvironment(
        scenario=scenario, buyer=ToolAwareBuyer(), seller=ScriptedSeller()
    )
    seller_state = env._context_for(Role.SELLER).private_state
    buyer_state = env._context_for(Role.BUYER).private_state
    assert seller_state["true_condition"] == "screen has a hidden hairline crack"
    assert "true_condition" not in buyer_state
    # Public claim (product.condition) remains visible to both via the product.
    assert "true_condition" not in to_jsonable(env._context_for(Role.BUYER).scenario.product)


def test_scenario_artifact_round_trips_true_condition():
    scenario = _scenario(seller_true_condition="battery swollen, undisclosed")
    artifact = ScenarioArtifact.from_scenario(scenario, scenario_id="s1")
    restored = ScenarioArtifact.from_mapping(json.loads(json.dumps(to_jsonable(artifact))))
    assert restored.seller_true_condition == "battery swollen, undisclosed"
    assert restored.to_scenario().seller_true_condition == "battery swollen, undisclosed"


def test_coach_case_red_line_excludes_true_condition_for_buyer(tmp_path):
    scenario = generate_scenarios(
        load_products("examples/data/real_market_products.json"), seed=13
    )[0]
    scenario = Scenario(
        product=scenario.product,
        buyer_budget=scenario.buyer_budget,
        seller_reservation_price=scenario.seller_reservation_price,
        max_turns=scenario.max_turns,
        seller_true_condition="refurbished, sold as new",
        metadata=scenario.metadata,
    )
    env = NegotiationEnvironment(
        scenario=scenario, buyer=ToolAwareBuyer(), seller=ScriptedSeller()
    )
    result = env.run()
    paths = write_run_artifacts(
        result=result,
        output_dir=tmp_path,
        run_id="asym-run",
        agents={
            "buyer": {"name": "tool_aware_buyer", "kind": "scripted"},
            "seller": {"name": "scripted_seller", "kind": "scripted"},
        },
        tool_regime={},
    )

    buyer_case = build_coach_case(paths.output_dir, user_role=Role.BUYER)
    seller_case = build_coach_case(paths.output_dir, user_role=Role.SELLER)

    assert "refurbished, sold as new" not in json.dumps(to_jsonable(buyer_case))
    assert "true_condition" not in buyer_case.user_private
    assert seller_case.user_private["true_condition"] == "refurbished, sold as new"
