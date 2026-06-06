import json

from opennego.cli import main
from opennego.evolution import STRATEGY_EVOLUTION_SCHEMA_VERSION
from opennego.leaderboard import LEADERBOARD_SCHEMA_VERSION
from opennego.learning import POLICY_LEARNING_SCHEMA_VERSION
from opennego.demo import (
    DEMO_BUNDLE_SCHEMA_VERSION,
    DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION,
    LEGACY_MVP_DEMO_BUNDLE_SCHEMA_VERSION,
    run_demo,
    run_mvp_demo,
    validate_demo_bundle,
)


def test_run_demo_generates_benchmark_learning_and_report(tmp_path):
    output_dir = tmp_path / "demo"
    report_path = tmp_path / "opennegotiation_demo.html"

    summary = run_demo(output_dir=output_dir, report_path=report_path)

    assert summary.name == "opennegotiation_demo"
    assert summary.benchmark_completed == 3
    assert summary.benchmark_failed == 0
    assert (output_dir / "demo_manifest.json").exists()
    assert (output_dir / "leaderboard_summary.json").exists()
    assert (output_dir / "battle_report.json").exists()
    assert (output_dir / "strategy_candidate.json").exists()
    assert report_path.exists()

    bundle_manifest = json.loads((output_dir / "demo_manifest.json").read_text())
    leaderboard = json.loads((output_dir / "leaderboard_summary.json").read_text())
    battle_report = json.loads((output_dir / "battle_report.json").read_text())
    candidate = json.loads((output_dir / "strategy_candidate.json").read_text())
    html = report_path.read_text()

    assert summary.bundle_manifest == str(output_dir / "demo_manifest.json")
    assert summary.leaderboard_summary == str(output_dir / "leaderboard_summary.json")
    assert bundle_manifest["schema_version"] == DEMO_BUNDLE_SCHEMA_VERSION
    assert bundle_manifest["benchmark"]["completed"] == 3
    assert bundle_manifest["benchmark"]["failed"] == 0
    assert bundle_manifest["benchmark"]["learning_run_id"].endswith("-no_tools-seed-13")
    assert bundle_manifest["artifacts"] == {
        "leaderboard_summary": str(output_dir / "leaderboard_summary.json"),
        "battle_report": str(output_dir / "battle_report.json"),
        "strategy_candidate": str(output_dir / "strategy_candidate.json"),
        "html_report": str(report_path),
    }
    assert bundle_manifest["artifact_schema_versions"] == {
        "leaderboard_summary": LEADERBOARD_SCHEMA_VERSION,
        "battle_report": POLICY_LEARNING_SCHEMA_VERSION,
        "strategy_candidate": STRATEGY_EVOLUTION_SCHEMA_VERSION,
    }
    assert bundle_manifest["expected_schema_versions"] == (
        bundle_manifest["artifact_schema_versions"]
    )
    assert bundle_manifest["workflow_steps"] == [
        "benchmark",
        "leaderboard",
        "policy_learning",
        "strategy_evolution",
        "html_report",
    ]
    assert leaderboard["schema_version"] == LEADERBOARD_SCHEMA_VERSION
    assert leaderboard["run_count"] == 3
    assert leaderboard["participant_summaries"]
    assert battle_report["opponent_profile_id"] == "seller_hardline_anchor_v1"
    assert candidate["parent_strategy_id"] == "buyer_baseline"
    assert "buyer_overpaid_market" in candidate["applied_lesson_ids"]
    lesson_ids = {lesson["id"] for lesson in battle_report["lessons"]}
    assert "buyer_overpaid_market" in lesson_ids
    assert "Leaderboard Preview" in html
    assert f"Leaderboard artifact {LEADERBOARD_SCHEMA_VERSION}" in html
    assert "Participant Coverage" in html
    assert "Training / Prompt Optimization" in html
    assert "Strategy Marketplace" in html
    assert "Hardline Anchor Seller" in html


def test_demo_cli_prints_artifact_paths(tmp_path, capsys):
    output_dir = tmp_path / "cli_demo"
    report_path = tmp_path / "cli_demo.html"

    status = main(
        [
            "demo",
            "--output-dir",
            str(output_dir),
            "--report",
            str(report_path),
        ]
    )
    stdout = capsys.readouterr().out

    payload = json.loads(stdout)
    assert status == 0
    assert payload["benchmark_completed"] == 3
    assert payload["benchmark_failed"] == 0
    assert payload["bundle_manifest"] == str(output_dir / "demo_manifest.json")
    assert payload["leaderboard_summary"] == str(
        output_dir / "leaderboard_summary.json"
    )
    assert payload["battle_report"] == str(output_dir / "battle_report.json")
    assert payload["strategy_candidate"] == str(output_dir / "strategy_candidate.json")
    assert payload["html_report"] == str(report_path)
    assert (output_dir / "leaderboard_summary.json").exists()
    assert (output_dir / "demo_manifest.json").exists()
    assert report_path.exists()


def test_validate_demo_bundle_passes_for_generated_demo(tmp_path):
    output_dir = tmp_path / "demo"
    summary = run_demo(output_dir=output_dir)

    result = validate_demo_bundle(summary.bundle_manifest)

    assert result.schema_version == DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION
    assert result.status == "passed"
    assert result.bundle_schema_version == DEMO_BUNDLE_SCHEMA_VERSION
    assert result.errors == ()
    assert result.artifact_schema_versions == {
        "leaderboard_summary": LEADERBOARD_SCHEMA_VERSION,
        "battle_report": POLICY_LEARNING_SCHEMA_VERSION,
        "strategy_candidate": STRATEGY_EVOLUTION_SCHEMA_VERSION,
    }
    assert result.artifacts["html_report"].endswith("opennegotiation_demo.html")


def test_validate_demo_bundle_cli_reports_pass_and_fail(tmp_path, capsys):
    output_dir = tmp_path / "demo"
    summary = run_demo(output_dir=output_dir)

    pass_code = main(["validate-demo", "--manifest", summary.bundle_manifest])
    pass_payload = json.loads(capsys.readouterr().out)

    assert pass_code == 0
    assert pass_payload["status"] == "passed"
    assert pass_payload["schema_version"] == DEMO_BUNDLE_VALIDATION_SCHEMA_VERSION

    (output_dir / "strategy_candidate.json").unlink()

    fail_code = main(["validate-demo", "--manifest", summary.bundle_manifest])
    fail_payload = json.loads(capsys.readouterr().out)

    assert fail_code == 1
    assert fail_payload["status"] == "failed"
    assert any("strategy_candidate" in item for item in fail_payload["errors"])


def test_validate_demo_bundle_fails_on_schema_mismatch(tmp_path):
    output_dir = tmp_path / "demo"
    summary = run_demo(output_dir=output_dir)
    battle_report_path = output_dir / "battle_report.json"
    battle_report = json.loads(battle_report_path.read_text())
    battle_report["schema_version"] = "wrong.schema"
    battle_report_path.write_text(json.dumps(battle_report, indent=2) + "\n")

    result = validate_demo_bundle(summary.bundle_manifest)

    assert result.status == "failed"
    assert any("battle_report.schema_version" in item for item in result.errors)
    assert result.artifact_schema_versions["battle_report"] == "wrong.schema"


def test_validate_demo_bundle_fails_on_workflow_order_drift(tmp_path):
    output_dir = tmp_path / "demo"
    summary = run_demo(output_dir=output_dir)
    manifest_path = output_dir / "demo_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["workflow_steps"] = ["benchmark", "html_report"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    result = validate_demo_bundle(summary.bundle_manifest)

    assert result.status == "failed"
    assert any("workflow_steps" in item for item in result.errors)


def test_validate_demo_bundle_reports_malformed_manifest(tmp_path):
    manifest_path = tmp_path / "bad_manifest.json"
    manifest_path.write_text("{not valid json\n")

    result = validate_demo_bundle(manifest_path)

    assert result.status == "failed"
    assert result.bundle_schema_version is None
    assert any("manifest: cannot read JSON object" in item for item in result.errors)


def test_legacy_mvp_demo_cli_still_works(tmp_path, capsys):
    output_dir = tmp_path / "legacy_mvp"

    status = main(["mvp-demo", "--output-dir", str(output_dir)])
    payload = json.loads(capsys.readouterr().out)

    assert status == 0
    assert payload["name"] == "opennego_mvp_demo"
    assert payload["bundle_manifest"] == str(output_dir / "mvp_demo_manifest.json")
    assert (output_dir / "mvp_demo_manifest.json").exists()

    manifest = json.loads((output_dir / "mvp_demo_manifest.json").read_text())
    assert manifest["schema_version"] == LEGACY_MVP_DEMO_BUNDLE_SCHEMA_VERSION

    validate_code = main(
        ["validate-demo-bundle", "--manifest", payload["bundle_manifest"]]
    )
    validate_payload = json.loads(capsys.readouterr().out)

    assert validate_code == 0
    assert validate_payload["status"] == "passed"
