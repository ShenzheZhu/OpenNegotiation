import json
from pathlib import Path

import pytest

from opennego.cli import main
from opennego.evolution import write_strategy_candidate
from opennego.learning import StrategyProfile, load_strategy_registry
from opennego.learning import write_battle_report
from opennego.marketplace import (
    MARKETPLACE_PROFILE_SCHEMA_VERSION,
    MARKETPLACE_VALIDATION_SCHEMA_VERSION,
    STRATEGY_CONFIG_SCHEMA_VERSION,
    MarketplaceError,
    install_marketplace_profile,
    load_marketplace_profile,
    validate_marketplace_configs,
    write_marketplace_profile,
)
from opennego.runner import run_experiment_config


def test_marketplace_export_turns_candidate_into_profile(tmp_path):
    candidate_path = _write_candidate(tmp_path)
    profile_path = tmp_path / "marketplace_profile.json"

    result = write_marketplace_profile(
        candidate_path,
        profile_path,
        profile_id="buyer_market_guard_v1",
        name="Buyer Market Guard",
        tags=("demo",),
        allowed_tools=("market_price_search",),
    )
    payload = json.loads(profile_path.read_text())
    profile = load_marketplace_profile(profile_path)
    direct_profile = StrategyProfile.from_mapping(payload)

    assert result.profile_id == "buyer_market_guard_v1"
    assert result.profile_path == str(profile_path)
    assert payload["schema_version"] == MARKETPLACE_PROFILE_SCHEMA_VERSION
    assert payload["id"] == "buyer_market_guard_v1"
    assert payload["role"] == "buyer"
    assert payload["name"] == "Buyer Market Guard"
    assert payload["allowed_tools"] == ["market_price_search"]
    assert "buyer_overpaid_market" in payload["metadata"]["applied_lesson_ids"]
    assert payload["metadata"]["candidate_id"] == "buyer_baseline-iter-1"
    assert profile.id == direct_profile.id == "buyer_market_guard_v1"


def test_marketplace_install_appends_and_rejects_duplicate_ids(tmp_path):
    candidate_path = _write_candidate(tmp_path)
    profile_path = tmp_path / "marketplace_profile.json"
    registry_path = tmp_path / "registry.json"
    write_marketplace_profile(
        candidate_path,
        profile_path,
        profile_id="buyer_market_guard_v1",
    )
    profile = json.loads(profile_path.read_text())

    installed = install_marketplace_profile(profile, registry_path)
    registry = load_strategy_registry(installed)
    installed_payload = json.loads(registry_path.read_text())
    installed_profile = installed_payload["profiles"][0]

    assert installed == registry_path
    assert registry.by_id("buyer_market_guard_v1").role.value == "buyer"
    assert installed_profile["schema_version"] == MARKETPLACE_PROFILE_SCHEMA_VERSION
    assert (
        installed_profile["metadata"]["strategy_config_version"]
        == STRATEGY_CONFIG_SCHEMA_VERSION
    )
    assert installed_profile["metadata"]["prompt_layers"]["base_prompt"] == {
        "field": "base_prompt",
        "editable": False,
        "scope": "sandbox_protocol",
    }
    assert installed_profile["metadata"]["prompt_layers"]["strategy_prompt"] == {
        "field": "strategy_prompt",
        "editable": True,
        "scope": "strategy_policy",
    }
    with pytest.raises(MarketplaceError, match="already exists"):
        install_marketplace_profile(profile, registry_path)

    profile["name"] = "Buyer Market Guard Updated"
    install_marketplace_profile(profile, registry_path, overwrite=True)
    updated = load_strategy_registry(registry_path)
    assert (
        updated.by_id("buyer_market_guard_v1").name
        == "Buyer Market Guard Updated"
    )


def test_marketplace_export_cli_installs_profile_for_strategy_listing(tmp_path, capsys):
    candidate_path = _write_candidate(tmp_path)
    profile_path = tmp_path / "profile.json"
    registry_path = tmp_path / "registry.json"

    status = main(
        [
            "marketplace-export",
            "--candidate",
            str(candidate_path),
            "--output",
            str(profile_path),
            "--profile-id",
            "shared_buyer_guard",
            "--name",
            "Shared Buyer Guard",
            "--tag",
            "external",
            "--install-registry",
            str(registry_path),
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    strategies_status = main(
        ["strategies", "--registry", str(registry_path), "--role", "buyer"]
    )
    strategies_stdout = capsys.readouterr().out

    assert status == 0
    assert payload["profile_id"] == "shared_buyer_guard"
    assert payload["installed_registry"] == str(registry_path)
    assert profile_path.exists()
    assert strategies_status == 0
    assert "shared_buyer_guard" in strategies_stdout


def test_marketplace_validation_accepts_curated_registry():
    result = validate_marketplace_configs(
        registry_path="examples/data/npc_strategies.json",
    )

    assert result.schema_version == MARKETPLACE_VALIDATION_SCHEMA_VERSION
    assert result.status == "passed"
    assert result.profile_count == 20
    assert result.errors == ()


def test_marketplace_validation_accepts_exported_and_installed_profile(
    tmp_path,
    capsys,
):
    candidate_path = _write_candidate(tmp_path)
    profile_path = tmp_path / "profile.json"
    registry_path = tmp_path / "registry.json"
    write_marketplace_profile(
        candidate_path,
        profile_path,
        profile_id="buyer_market_guard_v1",
        install_registry_path=registry_path,
    )

    result = validate_marketplace_configs(
        registry_path=registry_path,
        profile_paths=(profile_path,),
    )
    cli_status = main(
        [
            "validate-marketplace",
            "--registry",
            str(registry_path),
            "--profile",
            str(profile_path),
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)

    assert result.status == "passed"
    assert result.profile_count == 2
    assert result.errors == ()
    assert cli_status == 0
    assert cli_payload["schema_version"] == MARKETPLACE_VALIDATION_SCHEMA_VERSION
    assert cli_payload["status"] == "passed"


def test_marketplace_validation_fails_malformed_strategy_metadata(
    tmp_path,
    capsys,
):
    registry = json.loads(Path("examples/data/npc_strategies.json").read_text())
    registry["profiles"][0]["metadata"]["base_prompt_fixed"] = False
    registry["profiles"][0]["metadata"].pop("strategy_config_version")
    registry_path = tmp_path / "bad_registry.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n")

    result = validate_marketplace_configs(registry_path=registry_path)
    cli_status = main(["validate-marketplace", "--registry", str(registry_path)])
    cli_payload = json.loads(capsys.readouterr().out)

    assert result.status == "failed"
    assert any("base_prompt_fixed" in item for item in result.errors)
    assert any("strategy_config_version" in item for item in result.errors)
    assert cli_status == 1
    assert cli_payload["status"] == "failed"


def _write_candidate(tmp_path):
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
