import json

from opennego.cli import main
from opennego.market_sources import (
    MARKET_SOURCE_POLICY_SCHEMA_VERSION,
    MARKET_SOURCE_VALIDATION_SCHEMA_VERSION,
    validate_market_source_policy,
    write_market_source_policy,
)


def test_market_source_policy_validates_offline_export_boundary(tmp_path):
    policy_path = tmp_path / "source_policy.json"

    policy = write_market_source_policy(
        policy_path,
        source_id="ebay_offline_export",
        adapter_kind="offline_export",
        collection_mode="offline_export",
        data_rights="user_provided_export",
    )
    payload = json.loads(policy_path.read_text())
    result = validate_market_source_policy(policy_path)

    assert policy.schema_version == MARKET_SOURCE_POLICY_SCHEMA_VERSION
    assert payload["live_collection_enabled"] is False
    assert "raw_html" in payload["prohibited_fields"]
    assert result.schema_version == MARKET_SOURCE_VALIDATION_SCHEMA_VERSION
    assert result.status == "passed"
    assert result.errors == ()


def test_market_source_policy_rejects_unbounded_live_collection(tmp_path):
    policy_path = tmp_path / "bad_live_policy.json"
    write_market_source_policy(
        policy_path,
        source_id="ebay_live",
        adapter_kind="offline_export",
        collection_mode="offline_export",
        data_rights="user_provided_export",
        live_collection_enabled=True,
    )

    result = validate_market_source_policy(policy_path)

    assert result.status == "failed"
    assert any("live_collection_enabled requires collection_mode" in item for item in result.errors)
    assert any("live_collection_enabled requires terms_url" in item for item in result.errors)
    assert any("requires explicit official or licensed" in item for item in result.errors)


def test_market_source_policy_cli_generates_and_validates(tmp_path, capsys):
    policy_path = tmp_path / "source_policy.json"

    create_status = main(
        [
            "market-source-policy",
            "--output",
            str(policy_path),
            "--source-id",
            "ebay_offline_export",
        ]
    )
    create_payload = json.loads(capsys.readouterr().out)
    validate_status = main(
        [
            "validate-market-source",
            "--policy",
            str(policy_path),
        ]
    )
    validation_payload = json.loads(capsys.readouterr().out)

    assert create_status == 0
    assert create_payload["schema_version"] == MARKET_SOURCE_POLICY_SCHEMA_VERSION
    assert validate_status == 0
    assert validation_payload["status"] == "passed"
