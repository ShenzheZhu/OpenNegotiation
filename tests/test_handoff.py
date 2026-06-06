import json

from opennego.cli import main
from opennego.handoff import (
    EXTERNAL_HANDOFF_SCHEMA_VERSION,
    run_external_handoff_package,
)
from opennego.market_validation import MARKET_VALIDATION_SCHEMA_VERSION
from opennego.marketplace import MARKETPLACE_VALIDATION_SCHEMA_VERSION
from opennego.demo import DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION
from opennego.role_swap import ROLE_SWAP_SCHEMA_VERSION


def test_external_handoff_package_writes_validated_artifacts(tmp_path):
    output_dir = tmp_path / "handoff"

    summary = run_external_handoff_package(output_dir=output_dir)
    manifest = json.loads((output_dir / "handoff_manifest.json").read_text())
    readme = (output_dir / "README.md").read_text()
    demo_validation = json.loads(
        (output_dir / "validations" / "demo_bundle_validation.json").read_text()
    )
    market_validation = json.loads(
        (output_dir / "validations" / "market_validation.json").read_text()
    )
    marketplace_validation = json.loads(
        (output_dir / "validations" / "marketplace_validation.json").read_text()
    )
    role_swap = json.loads(
        (output_dir / "role_swap" / "role_swap_summary.json").read_text()
    )

    assert summary.schema_version == EXTERNAL_HANDOFF_SCHEMA_VERSION
    assert summary.status == "passed"
    assert manifest["schema_version"] == EXTERNAL_HANDOFF_SCHEMA_VERSION
    assert manifest["status"] == "passed"
    assert manifest["demo"]["benchmark_completed"] == 3
    assert manifest["demo"]["benchmark_failed"] == 0
    assert manifest["role_swap"]["participant_role_coverage"] == 1.0
    assert manifest["validations"]["demo_bundle"]["status"] == "passed"
    assert manifest["validations"]["market_dataset"]["status"] == "passed"
    assert manifest["validations"]["strategy_marketplace"]["status"] == "passed"
    assert demo_validation["schema_version"] == DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION
    assert market_validation["schema_version"] == MARKET_VALIDATION_SCHEMA_VERSION
    assert marketplace_validation["schema_version"] == MARKETPLACE_VALIDATION_SCHEMA_VERSION
    assert role_swap["schema_version"] == ROLE_SWAP_SCHEMA_VERSION
    assert (output_dir / "README.md").exists()
    assert (output_dir / "reports" / "opennegotiation_demo.html").exists()
    assert (output_dir / "demo" / "demo_manifest.json").exists()
    assert "OpenNegotiation External Handoff Package" in readme
    assert "fixture-backed" in readme
    assert "no live model-provider calls" in readme


def test_handoff_cli_prints_summary(tmp_path, capsys):
    output_dir = tmp_path / "cli_handoff"

    status = main(["handoff", "--output-dir", str(output_dir)])
    payload = json.loads(capsys.readouterr().out)

    assert status == 0
    assert payload["schema_version"] == EXTERNAL_HANDOFF_SCHEMA_VERSION
    assert payload["status"] == "passed"
    assert payload["readme"] == str(output_dir / "README.md")
    assert payload["manifest_path"] == str(output_dir / "handoff_manifest.json")
    assert payload["validations"]["demo_bundle"]["status"] == "passed"
    assert payload["validations"]["market_dataset"]["status"] == "passed"
    assert payload["validations"]["strategy_marketplace"]["status"] == "passed"
    assert (output_dir / "README.md").exists()
