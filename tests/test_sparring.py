import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from opennego.cli import main
from opennego.evolution import (
    STRATEGY_EVOLUTION_SCHEMA_VERSION,
    write_strategy_candidate,
)
from opennego.learning import write_battle_report
from opennego.runner import run_experiment_config
from opennego.schema import AgentAction, AgentContext, Role
from opennego.sparring import (
    SPARRING_EXECUTION_MODE,
    SPARRING_SUITE_SCHEMA_VERSION,
    run_sparring_suite,
)


def test_run_sparring_suite_writes_profile_reports(tmp_path):
    output_dir = tmp_path / "sparring"

    summary = run_sparring_suite(
        output_dir=output_dir,
        opponent_profile_ids=(
            "seller_hardline_anchor_v1",
            "seller_hidden_fees_v1",
        ),
    )

    payload = json.loads((output_dir / "sparring_suite.json").read_text())
    profile_ids = {result.profile_id for result in summary.results}

    assert summary.schema_version == SPARRING_SUITE_SCHEMA_VERSION
    assert summary.execution_mode == SPARRING_EXECUTION_MODE
    assert summary.completed == 2
    assert summary.failed == 0
    assert profile_ids == {"seller_hardline_anchor_v1", "seller_hidden_fees_v1"}
    assert payload["schema_version"] == SPARRING_SUITE_SCHEMA_VERSION
    assert payload["completed"] == 2

    for result in summary.results:
        battle_report_path = (
            output_dir / "profiles" / result.profile_id / "battle_report.json"
        )
        learning_dir = result.learning_input_dir
        assert learning_dir is not None
        manifest = json.loads((Path(learning_dir) / "manifest.json").read_text())
        trace = (Path(learning_dir) / "trace.jsonl").read_text()

        assert result.status == "completed"
        assert result.benchmark_completed == 3
        assert result.benchmark_failed == 0
        assert result.battle_report == str(battle_report_path)
        assert battle_report_path.exists()
        assert "buyer_overpaid_market" in result.lesson_ids
        assert manifest["agents"]["seller"]["profile_id"] == result.profile_id
        assert f"npc_seller:{result.profile_id}" in trace


def test_sparring_suite_rejects_wrong_role_profile(tmp_path):
    with pytest.raises(ValueError, match="expected seller profile"):
        run_sparring_suite(
            output_dir=tmp_path / "sparring",
            user_role="buyer",
            opponent_profile_ids=("buyer_budget_probe_v1",),
        )


def test_sparring_suite_supports_seller_user_against_buyer_profile(tmp_path):
    output_dir = tmp_path / "seller_sparring"

    summary = run_sparring_suite(
        output_dir=output_dir,
        user_role="seller",
        opponent_profile_ids=("buyer_budget_probe_v1",),
    )
    result = summary.results[0]
    assert result.learning_input_dir is not None
    manifest = json.loads(
        (Path(result.learning_input_dir) / "manifest.json").read_text()
    )
    trace = (Path(result.learning_input_dir) / "trace.jsonl").read_text()

    assert summary.completed == 1
    assert summary.failed == 0
    assert summary.user_role.value == "seller"
    assert result.profile_id == "buyer_budget_probe_v1"
    assert manifest["agents"]["buyer"]["profile_id"] == "buyer_budget_probe_v1"
    assert manifest["agents"]["seller"]["kind"] == "user_seller"
    assert "npc_buyer:buyer_budget_probe_v1" in trace


def test_sparring_suite_applies_user_strategy_candidate_to_buyer_policy(tmp_path):
    candidate_path = _write_buyer_strategy_candidate(tmp_path)
    output_dir = tmp_path / "strategy_sparring"

    summary = run_sparring_suite(
        output_dir=output_dir,
        opponent_profile_ids=("seller_hardline_anchor_v1",),
        user_strategy_path=candidate_path,
    )
    result = summary.results[0]
    assert result.learning_input_dir is not None
    manifest = json.loads(
        (Path(result.learning_input_dir) / "manifest.json").read_text()
    )
    metrics = json.loads((Path(result.learning_input_dir) / "metrics.json").read_text())
    trace = (Path(result.learning_input_dir) / "trace.jsonl").read_text()

    assert summary.user_strategy_candidate_id == "buyer_baseline-iter-1"
    assert summary.user_strategy_path == str(candidate_path)
    assert result.user_strategy_candidate_id == "buyer_baseline-iter-1"
    assert result.deal_price <= 575.0 * 1.05
    assert metrics["deal_price"] <= 575.0 * 1.05
    assert manifest["agents"]["buyer"]["kind"] == "strategy_candidate_buyer"
    assert manifest["agents"]["buyer"]["candidate_id"] == "buyer_baseline-iter-1"
    assert manifest["metadata"]["user_strategy"]["enabled"] is True
    assert "user_buyer:buyer_baseline-iter-1" in trace


def test_sparring_suite_accepts_custom_user_agent_factory(tmp_path):
    output_dir = tmp_path / "custom_sparring"

    summary = run_sparring_suite(
        output_dir=output_dir,
        opponent_profile_ids=("seller_hardline_anchor_v1",),
        user_agent_factory=custom_buyer_factory,
        user_agent_kind="external_fixed_buyer",
    )
    result = summary.results[0]
    assert result.learning_input_dir is not None
    manifest = json.loads(
        (Path(result.learning_input_dir) / "manifest.json").read_text()
    )
    trace = (Path(result.learning_input_dir) / "trace.jsonl").read_text()

    assert summary.user_agent_kind == "external_fixed_buyer"
    assert result.user_agent_kind == "external_fixed_buyer"
    assert summary.completed == 1
    assert summary.failed == 0
    assert manifest["agents"]["buyer"]["kind"] == "external_fixed_buyer"
    assert manifest["agents"]["buyer"]["name"] == "external_spar_buyer"
    assert "external_spar_buyer" in trace


def test_sparring_suite_rejects_wrong_role_custom_user_agent(tmp_path):
    output_dir = tmp_path / "bad_custom_sparring"

    with pytest.raises(ValueError, match="expected 'buyer'"):
        run_sparring_suite(
            output_dir=output_dir,
            opponent_profile_ids=("seller_hardline_anchor_v1",),
            user_agent_factory=wrong_role_user_factory,
        )

    assert not output_dir.exists()


def test_sparring_suite_rejects_user_strategy_and_custom_agent_combo(tmp_path):
    with pytest.raises(ValueError, match="cannot both be provided"):
        run_sparring_suite(
            output_dir=tmp_path / "combo_sparring",
            opponent_profile_ids=("seller_hardline_anchor_v1",),
            user_strategy_path=tmp_path / "strategy_candidate.json",
            user_agent_factory=custom_buyer_factory,
        )


def test_sparring_suite_rejects_wrong_role_user_strategy(tmp_path):
    candidate_path = tmp_path / "seller_candidate.json"
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": STRATEGY_EVOLUTION_SCHEMA_VERSION,
                "candidate_id": "seller_candidate-iter-1",
                "parent_strategy_id": "seller_candidate",
                "iteration": 1,
                "user_role": "seller",
                "source_battle_report": "battle_report.json",
                "source_run_id": "run-1",
                "scenario_id": "scenario-1",
                "opponent_profile_id": "buyer_budget_probe_v1",
                "strategy_prompt": "seller patch",
                "applied_lesson_ids": ["seller_undersold_market"],
                "applied_patches": ["Tighten seller floor."],
                "expected_improvements": ["price discipline"],
                "evaluation_plan": {},
                "metadata": {},
            },
            indent=2,
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="does not match user_role"):
        run_sparring_suite(
            output_dir=tmp_path / "sparring",
            user_role="buyer",
            opponent_profile_ids=("seller_hardline_anchor_v1",),
            user_strategy_path=candidate_path,
        )


def test_spar_cli_prints_suite_artifact(tmp_path, capsys):
    output_dir = tmp_path / "cli_spar"

    status = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert status == 0
    assert payload["schema_version"] == SPARRING_SUITE_SCHEMA_VERSION
    assert payload["completed"] == 1
    assert payload["failed"] == 0
    assert payload["artifact_path"] == str(output_dir / "sparring_suite.json")
    assert (output_dir / "sparring_suite.json").exists()


def test_spar_cli_accepts_user_strategy_candidate(tmp_path, capsys):
    candidate_path = _write_buyer_strategy_candidate(tmp_path)
    output_dir = tmp_path / "cli_strategy_spar"

    status = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
            "--user-strategy",
            str(candidate_path),
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert status == 0
    assert payload["user_strategy_candidate_id"] == "buyer_baseline-iter-1"
    assert payload["completed"] == 1


def test_spar_cli_rejects_wrong_role_profile(tmp_path, capsys):
    status = main(
        [
            "spar",
            "--output-dir",
            str(tmp_path / "cli_spar"),
            "--opponent-profile",
            "buyer_budget_probe_v1",
        ]
    )
    stdout = capsys.readouterr().out

    assert status == 2
    assert "expected seller profile" in stdout


def _write_buyer_strategy_candidate(tmp_path):
    runs_dir = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = (
        runs_dir
        / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"
    )
    battle_report_path = tmp_path / "battle_report.json"
    candidate_path = tmp_path / "strategy_candidate.json"
    write_battle_report(
        run_dir,
        battle_report_path,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    write_strategy_candidate(
        battle_report_path,
        candidate_path,
        parent_strategy_id="buyer_baseline",
    )
    return candidate_path


@dataclass
class CustomFixedBuyer:
    name: str = "external_spar_buyer"
    role: Role = Role.BUYER
    offer_price: float = 604.0

    def act(self, context: AgentContext) -> AgentAction:
        return AgentAction.offer_price(
            self.offer_price,
            f"My offer is ${self.offer_price:.2f}.",
        )


@dataclass
class WrongRoleUser:
    name: str = "wrong_role_user"
    role: Role = Role.SELLER

    def act(self, context: AgentContext) -> AgentAction:
        return AgentAction.reject("Wrong role.")


def custom_buyer_factory(role):
    return CustomFixedBuyer()


def wrong_role_user_factory(role):
    return WrongRoleUser()
