import json

from opennego.artifacts import write_json
from opennego.cli import main
from opennego.strategy_config import (
    STRATEGY_CONFIG_SCHEMA_VERSION,
    prompt_layer_contract,
)
from opennego.training_adapter import (
    TRAINING_ADAPTER_SCHEMA_VERSION,
    TRAINING_ADAPTER_VALIDATION_SCHEMA_VERSION,
    validate_training_adapter_package,
    write_training_adapter_package,
)


def test_training_adapter_package_preserves_strategy_config_contract(tmp_path):
    config_path = _write_strategy_config(tmp_path / "strategy_config.json")
    adapter_path = tmp_path / "adapter.json"

    package = write_training_adapter_package(
        config_path,
        adapter_path,
        agent_kind="team_buyer_agent",
        entrypoint_hint="/abs/path/agents.py:buyer_factory",
    )
    payload = json.loads(adapter_path.read_text())
    validation = validate_training_adapter_package(adapter_path)

    assert package.adapter_id == "team_buyer_agent:buyer_strategy:v2"
    assert payload["schema_version"] == TRAINING_ADAPTER_SCHEMA_VERSION
    assert payload["role"] == "buyer"
    assert payload["prompt_layers"] == prompt_layer_contract()
    assert payload["payload"]["strategy_prompt"] == "Stay under market reference."
    assert payload["metadata"]["base_prompt_fixed"] is True
    assert payload["metadata"]["strategy_prompt_editable"] is True
    assert payload["lineage"][0]["candidate_id"] == "candidate_001"
    assert payload["integration_contract"]["code_mutation"] is False
    assert payload["integration_contract"]["entrypoint_hint"] == (
        "/abs/path/agents.py:buyer_factory"
    )
    assert validation.schema_version == TRAINING_ADAPTER_VALIDATION_SCHEMA_VERSION
    assert validation.status == "passed"
    assert validation.errors == ()


def test_training_adapter_cli_exports_and_validates_package(tmp_path, capsys):
    config_path = _write_strategy_config(tmp_path / "strategy_config.json")
    adapter_path = tmp_path / "adapter.json"

    export_status = main(
        [
            "export-training-adapter",
            "--strategy-config",
            str(config_path),
            "--output",
            str(adapter_path),
            "--agent-kind",
            "team_buyer_agent",
            "--adapter-id",
            "team_buyer_adapter_v2",
        ]
    )
    export_payload = json.loads(capsys.readouterr().out)
    validate_status = main(
        [
            "validate-training-adapter",
            "--adapter",
            str(adapter_path),
        ]
    )
    validation_payload = json.loads(capsys.readouterr().out)

    assert export_status == 0
    assert export_payload["training_adapter"] == str(adapter_path)
    assert export_payload["adapter_id"] == "team_buyer_adapter_v2"
    assert export_payload["role"] == "buyer"
    assert validate_status == 0
    assert validation_payload["status"] == "passed"


def test_training_adapter_validation_rejects_code_mutation_contract(tmp_path):
    config_path = _write_strategy_config(tmp_path / "strategy_config.json")
    adapter_path = tmp_path / "adapter.json"
    write_training_adapter_package(
        config_path,
        adapter_path,
        agent_kind="team_buyer_agent",
    )
    payload = json.loads(adapter_path.read_text())
    payload["integration_contract"]["code_mutation"] = True
    adapter_path.write_text(json.dumps(payload) + "\n")

    result = validate_training_adapter_package(adapter_path)

    assert result.status == "failed"
    assert "integration_contract.code_mutation must be false" in result.errors


def _write_strategy_config(path):
    payload = {
        "schema_version": STRATEGY_CONFIG_SCHEMA_VERSION,
        "strategy_id": "buyer_strategy",
        "version": 2,
        "role": "buyer",
        "base_prompt": "Follow OpenNegotiation buyer protocol exactly.",
        "strategy_prompt": "Stay under market reference.",
        "prompt_layers": prompt_layer_contract(),
        "source_candidate_id": "candidate_001",
        "parent_strategy_id": "buyer_strategy_v1",
        "source_battle_report": "runs/battle_report.json",
        "source_run_id": "run_001",
        "scenario_id": "camera_001",
        "opponent_profile_id": "seller_anchor_v1",
        "applied_lesson_ids": ["buyer_overpaid_market"],
        "applied_patches": ["Use market reference before accepting."],
        "expected_improvements": ["Lower accepted price."],
        "lineage": [
            {
                "source_type": "strategy_candidate",
                "candidate_id": "candidate_001",
                "candidate_iteration": 2,
            }
        ],
        "metadata": {
            "base_prompt_fixed": True,
            "strategy_prompt_editable": True,
            "strategy_config_version": STRATEGY_CONFIG_SCHEMA_VERSION,
            "prompt_layers": prompt_layer_contract(),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    return path
