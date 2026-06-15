import json

import pytest

from opennego.cli import main
from opennego.evolution import write_strategy_candidate
from opennego.learning import write_battle_report
from opennego.runner import run_experiment_config
from opennego.strategy_config import write_strategy_config
from opennego.strategy_lineage import (
    STRATEGY_LINEAGE_SCHEMA_VERSION,
    append_strategy_config,
    load_strategy_lineage,
    validate_strategy_lineage,
)


def _candidate(tmp_path, name, parent_strategy_id, iteration):
    runs_dir = tmp_path / f"runs_{name}"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs_dir)
    run_dir = runs_dir / "real_market_demo-iphone_14_pro_128gb_unlocked_good-no_tools-seed-13"
    report_path = tmp_path / f"{name}_report.json"
    write_battle_report(
        run_dir, report_path, user_role="buyer",
        opponent_profile_id="seller_hardline_anchor_v1",
    )
    candidate_path = tmp_path / f"{name}_candidate.json"
    write_strategy_candidate(
        report_path, candidate_path,
        parent_strategy_id=parent_strategy_id, iteration=iteration,
    )
    return candidate_path


def test_two_apply_runs_form_a_linked_chain(tmp_path):
    lineage_path = tmp_path / "lineage.json"

    c1 = _candidate(tmp_path, "v1", "buyer_baseline", 1)
    config1 = tmp_path / "config_v1.json"
    from opennego.strategy_config import load_strategy_config

    write_strategy_config(c1, config1, strategy_id="buyer_strategy")
    append_strategy_config(lineage_path, load_strategy_config(config1), config1)

    c2 = _candidate(tmp_path, "v2", "buyer_strategy", 2)
    config2 = tmp_path / "config_v2.json"
    write_strategy_config(c2, config2, base_config_path=config1, strategy_id="buyer_strategy")
    append_strategy_config(lineage_path, load_strategy_config(config2), config2)

    lineage = load_strategy_lineage(lineage_path)
    assert lineage.schema_version == STRATEGY_LINEAGE_SCHEMA_VERSION
    assert lineage.strategy_id == "buyer_strategy"
    assert len(lineage.nodes) == 2
    assert lineage.nodes[0].parent_version is None
    assert lineage.nodes[1].parent_version == lineage.nodes[0].version
    assert validate_strategy_lineage(lineage_path) == ()


def test_lineage_cli_renders_chain(tmp_path, capsys):
    lineage_path = tmp_path / "lineage.json"
    c1 = _candidate(tmp_path, "v1", "buyer_baseline", 1)
    config1 = tmp_path / "config_v1.json"

    code = main(
        [
            "apply-strategy",
            "--candidate", str(c1),
            "--output", str(config1),
            "--strategy-id", "buyer_strategy",
            "--lineage", str(lineage_path),
        ]
    )
    apply_payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert apply_payload["lineage"] == str(lineage_path)

    code = main(["lineage", "--lineage", str(lineage_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "passed"
    assert payload["node_count"] == 1
    assert payload["chain"][0]["strategy_id"] == "buyer_strategy"
    assert payload["chain"][0]["decision"] == "accepted"


def test_validate_detects_broken_parent_link(tmp_path):
    lineage_path = tmp_path / "lineage.json"
    c1 = _candidate(tmp_path, "v1", "buyer_baseline", 1)
    config1 = tmp_path / "config_v1.json"
    from opennego.strategy_config import load_strategy_config

    write_strategy_config(c1, config1, strategy_id="buyer_strategy")
    append_strategy_config(lineage_path, load_strategy_config(config1), config1)

    data = json.loads(lineage_path.read_text())
    data["nodes"].append({
        **data["nodes"][0],
        "version": 5,
        "parent_version": 99,
    })
    lineage_path.write_text(json.dumps(data, indent=2) + "\n")

    errors = validate_strategy_lineage(lineage_path)
    assert any("parent_version" in error for error in errors)


def test_validate_detects_missing_config_artifact(tmp_path):
    lineage_path = tmp_path / "lineage.json"
    c1 = _candidate(tmp_path, "v1", "buyer_baseline", 1)
    config1 = tmp_path / "config_v1.json"
    from opennego.strategy_config import load_strategy_config

    write_strategy_config(c1, config1, strategy_id="buyer_strategy")
    append_strategy_config(lineage_path, load_strategy_config(config1), config1)
    config1.unlink()

    errors = validate_strategy_lineage(lineage_path)
    assert any("missing artifact" in error for error in errors)


def test_append_rejects_mismatched_strategy_id(tmp_path):
    from opennego.strategy_config import load_strategy_config
    from opennego.strategy_lineage import StrategyLineageError

    lineage_path = tmp_path / "lineage.json"
    c1 = _candidate(tmp_path, "v1", "buyer_baseline", 1)
    config1 = tmp_path / "config_v1.json"
    write_strategy_config(c1, config1, strategy_id="strategy_a")
    append_strategy_config(lineage_path, load_strategy_config(config1), config1)

    c2 = _candidate(tmp_path, "v2", "buyer_baseline", 1)
    config2 = tmp_path / "config_v2.json"
    write_strategy_config(c2, config2, strategy_id="strategy_b")

    with pytest.raises(StrategyLineageError, match="cannot append"):
        append_strategy_config(lineage_path, load_strategy_config(config2), config2)
