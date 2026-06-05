import json
from pathlib import Path

import pytest

from opennego.artifacts import load_manifest, load_metric_report
from opennego.runner import ConfigValidationError, run_experiment_config


def write_config(
    tmp_path: Path,
    output_dir: Path,
    *,
    products_file: str = "examples/data/products.json",
) -> Path:
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "runner_smoke",
        "output_dir": str(output_dir),
        "resume": True,
        "fail_fast": True,
        "seeds": [11],
        "agents": {
            "buyer": {"kind": "tool_aware_buyer"},
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": [
            {
                "id": "camera_001",
                "products_file": products_file,
                "product_index": 0,
                "max_turns": 8,
            }
        ],
        "tool_regimes": [
            {"id": "no_tools", "tools": []},
            {
                "id": "buyer_private_market_search",
                "tools": [
                    {
                        "name": "market_price_search",
                        "kind": "market_price",
                        "source": "examples/data/market_comps.json",
                        "visibility": "buyer_private",
                    }
                ],
            },
        ],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    return config_path


def read_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text())


def test_config_runner_writes_artifacts_and_resumes(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(tmp_path, output_dir)

    first = run_experiment_config(config_path)

    assert first.total_runs == 2
    assert first.completed == 2
    assert first.skipped == 0
    assert first.failed == 0

    no_tool_dir = output_dir / "runner_smoke-camera_001-no_tools-seed-11"
    tool_dir = output_dir / "runner_smoke-camera_001-buyer_private_market_search-seed-11"
    for run_dir in (no_tool_dir, tool_dir):
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "trace.jsonl").exists()
        assert (run_dir / "metrics.json").exists()

    manifest = load_manifest(tool_dir / "manifest.json")
    metrics = load_metric_report(tool_dir / "metrics.json")
    assert (
        manifest.run_id
        == "runner_smoke-camera_001-buyer_private_market_search-seed-11"
    )
    assert manifest.seed == 11
    assert manifest.tool_regime["id"] == "buyer_private_market_search"
    assert metrics.outcome == "deal"
    assert metrics.metrics["tool_call_count"] == 1.0

    second = run_experiment_config(config_path)

    assert second.completed == 0
    assert second.skipped == 2
    assert second.failed == 0


def test_config_runner_validates_all_inputs_before_creating_output(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(
        tmp_path,
        output_dir,
        products_file="missing/products.json",
    )

    with pytest.raises(ConfigValidationError, match="products_file does not exist"):
        run_experiment_config(config_path)

    assert not output_dir.exists()


def test_config_runner_rejects_unsupported_agent_before_creating_output(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(tmp_path, output_dir)
    config = read_config(config_path)
    config["agents"]["buyer"]["kind"] = "unsupported_buyer"
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    with pytest.raises(ConfigValidationError, match="unsupported_buyer"):
        run_experiment_config(config_path)

    assert not output_dir.exists()
