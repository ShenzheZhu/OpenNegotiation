import json

import pytest

from opennego.cli import main
from opennego.learning import write_battle_report
from opennego.runner import run_experiment_config
from opennego.strategy_config import (
    STRATEGY_CONFIG_SCHEMA_VERSION,
    StrategyConfigError,
    load_strategy_config,
    write_strategy_config,
)
from opennego.evolution import write_strategy_candidate


def test_apply_strategy_candidate_writes_versioned_strategy_config(tmp_path):
    candidate_path = _write_strategy_candidate(tmp_path, parent_strategy_id="buyer_base")
    config_path = tmp_path / "strategy_config.json"

    written = write_strategy_config(
        candidate_path,
        config_path,
        strategy_id="buyer_base_v1",
    )
    payload = json.loads(written.read_text())
    config = load_strategy_config(written)

    assert written == config_path
    assert payload["schema_version"] == STRATEGY_CONFIG_SCHEMA_VERSION
    assert payload["strategy_id"] == "buyer_base_v1"
    assert payload["version"] == 1
    assert payload["role"] == "buyer"
    assert payload["source_candidate_id"] == "buyer_base-iter-1"
    assert payload["metadata"]["base_prompt_fixed"] is True
    assert payload["metadata"]["strategy_prompt_editable"] is True
    assert payload["metadata"]["strategy_config_version"] == STRATEGY_CONFIG_SCHEMA_VERSION
    assert payload["prompt_layers"]["base_prompt"]["editable"] is False
    assert payload["prompt_layers"]["strategy_prompt"]["editable"] is True
    assert payload["metadata"]["prompt_layers"] == payload["prompt_layers"]
    assert payload["applied_lesson_ids"]
    assert payload["applied_patches"]
    assert payload["lineage"][0]["candidate_id"] == "buyer_base-iter-1"
    assert config.strategy_id == "buyer_base_v1"
    assert config.role.value == "buyer"


def test_apply_strategy_candidate_extends_existing_config_lineage(tmp_path):
    first_candidate = _write_strategy_candidate(tmp_path / "first", parent_strategy_id="buyer_base")
    first_config = tmp_path / "strategy_v1.json"
    write_strategy_config(first_candidate, first_config, strategy_id="buyer_strategy")
    second_candidate = _write_strategy_candidate(
        tmp_path / "second",
        parent_strategy_id="buyer_strategy",
        iteration=2,
    )
    second_config = tmp_path / "strategy_v2.json"

    write_strategy_config(
        second_candidate,
        second_config,
        base_config_path=first_config,
        strategy_id="buyer_strategy",
    )
    payload = json.loads(second_config.read_text())

    assert payload["strategy_id"] == "buyer_strategy"
    assert payload["version"] == 2
    assert len(payload["lineage"]) == 2
    assert payload["metadata"]["previous_strategy_id"] == "buyer_strategy"
    assert payload["metadata"]["previous_strategy_version"] == 1
    assert payload["base_prompt"] == json.loads(first_config.read_text())["base_prompt"]


def test_apply_strategy_cli_prints_config_summary(tmp_path, capsys):
    candidate_path = _write_strategy_candidate(tmp_path, parent_strategy_id="buyer_base")
    config_path = tmp_path / "cli_strategy_config.json"

    status = main(
        [
            "apply-strategy",
            "--candidate",
            str(candidate_path),
            "--output",
            str(config_path),
            "--strategy-id",
            "buyer_base_v1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 0
    assert payload == {
        "strategy_config": str(config_path),
        "strategy_id": "buyer_base_v1",
        "version": 1,
        "role": "buyer",
    }
    assert config_path.exists()


def test_strategy_config_loader_rejects_editable_base_prompt(tmp_path):
    candidate_path = _write_strategy_candidate(tmp_path, parent_strategy_id="buyer_base")
    config_path = tmp_path / "strategy_config.json"
    write_strategy_config(candidate_path, config_path)
    payload = json.loads(config_path.read_text())
    payload["prompt_layers"]["base_prompt"]["editable"] = True
    config_path.write_text(json.dumps(payload) + "\n")

    with pytest.raises(StrategyConfigError, match="prompt_layers.base_prompt.editable"):
        load_strategy_config(config_path)


def _write_strategy_candidate(tmp_path, *, parent_strategy_id: str, iteration: int = 1):
    tmp_path.mkdir(parents=True, exist_ok=True)
    runs_dir = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = (
        runs_dir
        / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"
    )
    report_path = tmp_path / "battle_report.json"
    write_battle_report(
        run_dir,
        report_path,
        user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    candidate_path = tmp_path / "strategy_candidate.json"
    write_strategy_candidate(
        report_path,
        candidate_path,
        parent_strategy_id=parent_strategy_id,
        iteration=iteration,
    )
    return candidate_path
