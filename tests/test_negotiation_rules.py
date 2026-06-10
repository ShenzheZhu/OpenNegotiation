import json
from dataclasses import dataclass, field

import pytest

from opennego.agents import ScriptedSeller, ToolAwareBuyer
from opennego.artifacts import to_jsonable
from opennego.environment import (
    RULES_ACTOR,
    NegotiationEnvironment,
    NegotiationRules,
)
from opennego.runner import (
    ConfigValidationError,
    negotiation_rules_metadata,
    run_experiment_config,
)
from opennego.schema import ActionType, AgentAction, Product, Role, Scenario


@dataclass
class SequenceAgent:
    """Replays a fixed action sequence, repeating the last action."""

    role: Role
    actions: tuple[AgentAction, ...]
    name: str = "sequence_agent"
    _cursor: int = field(default=0, repr=False)

    def act(self, context) -> AgentAction:
        action = self.actions[min(self._cursor, len(self.actions) - 1)]
        self._cursor += 1
        return action


def _scenario(max_turns: int = 8) -> Scenario:
    product = Product.from_mapping(
        json.loads(open("examples/data/products.json").read())[0]
    )
    return Scenario(
        product=product,
        buyer_budget=850.0,
        seller_reservation_price=620.0,
        max_turns=max_turns,
    )


def _rule_events(result):
    return [event for event in result.events if event.actor == RULES_ACTOR]


def test_step_loop_matches_run_for_default_rules():
    def build():
        return NegotiationEnvironment(
            scenario=_scenario(),
            buyer=ToolAwareBuyer(),
            seller=ScriptedSeller(),
        )

    run_env = build()
    step_env = build()

    run_result = run_env.run()
    while not step_env.is_complete:
        step_env.step()
    step_result = step_env.result

    assert json.dumps(to_jsonable(run_result), sort_keys=True) == json.dumps(
        to_jsonable(step_result), sort_keys=True
    )
    assert step_env.step() is None
    assert run_env.run() is run_result


def test_standing_offer_expires_and_cannot_be_accepted():
    buyer = SequenceAgent(
        role=Role.BUYER,
        actions=(AgentAction.offer_price(700.0), AgentAction.message("still there?")),
    )
    seller = SequenceAgent(
        role=Role.SELLER,
        actions=(AgentAction.message("let me think"), AgentAction.accept()),
    )
    env = NegotiationEnvironment(
        scenario=_scenario(),
        buyer=buyer,
        seller=seller,
        rules=NegotiationRules(offer_expiry_turns=1),
    )

    result = env.run()

    assert result.outcome == "invalid_accept"
    expiry_events = [
        event for event in _rule_events(result) if "offer_expired" in event.content
    ]
    assert len(expiry_events) == 1
    assert expiry_events[0].content == "offer_expired:buyer"
    assert expiry_events[0].role == Role.SYSTEM


def test_offer_within_expiry_window_is_accepted():
    buyer = SequenceAgent(role=Role.BUYER, actions=(AgentAction.offer_price(700.0),))
    seller = SequenceAgent(role=Role.SELLER, actions=(AgentAction.accept(),))
    env = NegotiationEnvironment(
        scenario=_scenario(),
        buyer=buyer,
        seller=seller,
        rules=NegotiationRules(offer_expiry_turns=1),
    )

    result = env.run()

    assert result.outcome == "deal"
    assert result.deal_price == 700.0
    assert _rule_events(result) == []


def test_offer_cap_ends_run_as_invalid_offer():
    buyer = SequenceAgent(
        role=Role.BUYER,
        actions=(AgentAction.offer_price(600.0), AgentAction.offer_price(610.0)),
    )
    seller = SequenceAgent(role=Role.SELLER, actions=(AgentAction.offer_price(800.0),))
    env = NegotiationEnvironment(
        scenario=_scenario(),
        buyer=buyer,
        seller=seller,
        rules=NegotiationRules(max_offers_per_side=1),
    )

    result = env.run()

    assert result.outcome == "invalid_offer"
    assert result.deal_price is None
    cap_events = [
        event for event in _rule_events(result) if "offer_cap_exceeded" in event.content
    ]
    assert [event.content for event in cap_events] == ["offer_cap_exceeded:buyer"]


def test_ghost_action_ends_run_as_ghosted():
    buyer = SequenceAgent(role=Role.BUYER, actions=(AgentAction.offer_price(400.0),))
    seller = SequenceAgent(role=Role.SELLER, actions=(AgentAction.ghost("lowball"),))
    env = NegotiationEnvironment(scenario=_scenario(), buyer=buyer, seller=seller)

    result = env.run()

    assert result.outcome == "ghosted"
    assert result.deal_price is None
    assert result.events[-1].action_type == ActionType.GHOST
    assert result.metrics["deal_rate"] == 0.0


def test_turn_delay_cost_recorded_in_metrics():
    buyer = SequenceAgent(role=Role.BUYER, actions=(AgentAction.offer_price(700.0),))
    seller = SequenceAgent(role=Role.SELLER, actions=(AgentAction.accept(),))
    env = NegotiationEnvironment(
        scenario=_scenario(),
        buyer=buyer,
        seller=seller,
        rules=NegotiationRules(turn_delay_cost=2.5),
    )

    result = env.run()

    assert result.completed_turns == 2
    assert result.metrics["turn_delay_cost_total"] == 5.0


def test_metrics_omit_delay_cost_without_rules():
    env = NegotiationEnvironment(
        scenario=_scenario(),
        buyer=ToolAwareBuyer(),
        seller=ScriptedSeller(),
    )

    result = env.run()

    assert "turn_delay_cost_total" not in result.metrics


def test_private_state_exposes_rule_budgets():
    buyer = SequenceAgent(role=Role.BUYER, actions=(AgentAction.offer_price(700.0),))
    seller = SequenceAgent(role=Role.SELLER, actions=(AgentAction.accept(),))
    env = NegotiationEnvironment(
        scenario=_scenario(),
        buyer=buyer,
        seller=seller,
        rules=NegotiationRules(offer_expiry_turns=2, max_offers_per_side=3),
    )

    before = env._context_for(Role.BUYER).private_state["negotiation_rules"]
    assert before["remaining_offers"] == 3
    assert before["offer_expiry_turns"] == 2

    env.step()

    after = env._context_for(Role.BUYER).private_state["negotiation_rules"]
    assert after["remaining_offers"] == 2
    assert after["standing_offer_age_turns"] == 0


def test_rules_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        NegotiationRules(offer_expiry_turns=0)
    with pytest.raises(ValueError):
        NegotiationRules(max_offers_per_side=-1)
    with pytest.raises(ValueError):
        NegotiationRules(turn_delay_cost=-0.1)


def test_runner_config_rules_block(tmp_path):
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "rules_smoke",
        "output_dir": str(tmp_path / "runs"),
        "seeds": [7],
        "agents": {
            "buyer": {"kind": "tool_aware_buyer"},
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": [
            {
                "id": "camera",
                "products_file": "examples/data/products.json",
                "max_turns": 8,
            }
        ],
        "rules": {"max_offers_per_side": 4, "turn_delay_cost": 1.0},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    summary = run_experiment_config(config_path)

    assert summary.completed == 1
    run_dir = tmp_path / "runs" / summary.runs[0].run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["metadata"]["rules"] == {
        "enabled": True,
        "offer_expiry_turns": None,
        "max_offers_per_side": 4,
        "turn_delay_cost": 1.0,
    }
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert "turn_delay_cost_total" in metrics["metrics"]


def test_runner_config_rejects_bad_rules_block(tmp_path):
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "rules_bad",
        "output_dir": str(tmp_path / "runs"),
        "agents": {
            "buyer": {"kind": "tool_aware_buyer"},
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": [
            {"id": "camera", "products_file": "examples/data/products.json"}
        ],
        "rules": {"max_offers_per_side": 0},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    with pytest.raises(ConfigValidationError, match="rules"):
        run_experiment_config(config_path)


def test_rules_metadata_disabled_by_default():
    assert negotiation_rules_metadata(None) == {"enabled": False}
