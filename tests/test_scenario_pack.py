import json

import pytest

from opennego.cli import main
from opennego.runner import run_experiment_config
from opennego.scenario_pack import (
    SCENARIO_PACK_SCHEMA_VERSION,
    ScenarioPackError,
    build_scenario_pack,
    validate_scenario_pack,
)

PRODUCTS = "examples/data/scenario_seed_products.json"
COMPS = "examples/data/scenario_seed_comps.json"


def _build(tmp_path, name="pack", **kwargs):
    return build_scenario_pack(
        products_file=PRODUCTS,
        market_comps_file=COMPS,
        output_dir=tmp_path / name,
        seed=kwargs.pop("seed", 13),
        **kwargs,
    )


def test_build_pack_writes_manifest_scenarios_and_config(tmp_path):
    summary = _build(tmp_path)

    manifest = json.loads(open(summary.manifest_file).read())
    scenarios = json.loads(open(summary.scenarios_file).read())
    config = json.loads(open(summary.experiment_config_file).read())

    assert summary.schema_version == SCENARIO_PACK_SCHEMA_VERSION
    assert manifest["schema_version"] == SCENARIO_PACK_SCHEMA_VERSION
    assert manifest["scenario_count"] == len(scenarios) == 6
    assert len(manifest["categories"]) >= 5
    assert manifest["market_validation_status"] == "passed"
    assert manifest["sources"]["products_file"]["sha256"]
    assert len(config["scenarios"]) == 6
    assert {regime["id"] for regime in config["tool_regimes"]} == {
        "no_tools",
        "buyer_private_market_search",
    }
    for entry in config["scenarios"]:
        assert entry["buyer_budget"] > 0
        assert entry["seller_reservation_price"] > 0
        assert entry["metadata"]["batna"]["schema_version"] == "opennego.batna.v1"


def test_build_pack_is_deterministic(tmp_path):
    first = _build(tmp_path, name="first")
    second = _build(tmp_path, name="second")

    assert (
        open(first.scenarios_file).read() == open(second.scenarios_file).read()
    )
    first_manifest = json.loads(open(first.manifest_file).read())
    second_manifest = json.loads(open(second.manifest_file).read())
    assert first_manifest == second_manifest


def test_emitted_config_runs_through_runner(tmp_path):
    summary = _build(tmp_path, scenarios_per_product=1)

    run_summary = run_experiment_config(
        summary.experiment_config_file,
        output_dir=tmp_path / "runs",
    )

    assert run_summary.failed == 0
    assert run_summary.completed == 12


def test_validate_pack_passes_then_fails_on_tampered_source(tmp_path):
    products_copy = tmp_path / "products.json"
    comps_copy = tmp_path / "comps.json"
    products_copy.write_text(open(PRODUCTS).read())
    comps_copy.write_text(open(COMPS).read())

    summary = build_scenario_pack(
        products_file=products_copy,
        market_comps_file=comps_copy,
        output_dir=tmp_path / "pack",
        seed=13,
    )

    assert validate_scenario_pack(summary.manifest_file).status == "passed"

    products_copy.write_text(open(PRODUCTS).read() + "\n")
    result = validate_scenario_pack(summary.manifest_file)
    assert result.status == "failed"
    assert any("fingerprint mismatch" in error for error in result.errors)


def test_validate_pack_fails_on_missing_artifact(tmp_path):
    summary = _build(tmp_path)
    (tmp_path / "pack" / "scenarios.json").unlink()

    result = validate_scenario_pack(summary.manifest_file)

    assert result.status == "failed"
    assert any("missing file" in error for error in result.errors)


def test_build_rejects_products_without_market_reference(tmp_path):
    with pytest.raises(ScenarioPackError, match="market_reference"):
        build_scenario_pack(
            products_file="examples/data/products.json",
            market_comps_file="examples/data/market_comps.json",
            output_dir=tmp_path / "pack",
            seed=13,
        )


def test_cli_scenarios_build_and_validate(tmp_path, capsys):
    build_code = main(
        [
            "scenarios",
            "build",
            "--products-file",
            PRODUCTS,
            "--market-comps-file",
            COMPS,
            "--output-dir",
            str(tmp_path / "pack"),
            "--seed",
            "21",
            "--name",
            "cli_pack",
        ]
    )
    build_payload = json.loads(capsys.readouterr().out)

    assert build_code == 0
    assert build_payload["name"] == "cli_pack"
    assert build_payload["scenario_count"] == 6

    validate_code = main(
        ["scenarios", "validate", "--manifest", build_payload["manifest_file"]]
    )
    validate_payload = json.loads(capsys.readouterr().out)

    assert validate_code == 0
    assert validate_payload["status"] == "passed"
