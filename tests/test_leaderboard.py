import json
import shutil

import pytest

from opennego.artifacts import load_manifest
from opennego.cli import main
from opennego.leaderboard import LEADERBOARD_SCHEMA_VERSION, build_leaderboard
from opennego.ports import LLMRequest, LLMResponse
from opennego.runner import run_experiment_config


class RoleAwareFakeLLM:
    def __init__(self):
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        role = request.metadata.get("agent_role")
        if role == "buyer":
            content = '{"type": "offer", "price": 760, "note": "Buyer offer."}'
        else:
            content = '{"type": "accept", "note": "Seller accepts."}'
        return LLMResponse(model=request.model, content=content)


def test_build_leaderboard_aggregates_real_market_role_tracks(tmp_path):
    output_dir = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=output_dir)

    summary = build_leaderboard(output_dir)
    buyer_track = _track(summary, "buyer", "tool_aware_buyer:tool_aware_buyer")
    seller_track = _track(summary, "seller", "scripted_seller:scripted_seller")
    buyer_summary = _participant(summary, "tool_aware_buyer:tool_aware_buyer")
    seller_summary = _participant(summary, "scripted_seller:scripted_seller")

    assert summary.schema_version == LEADERBOARD_SCHEMA_VERSION
    assert summary.run_count == 3
    assert len(summary.runs) == 3
    assert len(summary.participant_summaries) == 2
    assert [row.rank for row in summary.runs] == [1, 2, 3]
    assert all(row.score > 0 for row in summary.runs)
    assert buyer_track.rank == 1
    assert buyer_track.run_count == 3
    assert buyer_track.deal_rate == 1.0
    assert seller_track.run_count == 3
    assert buyer_track.average_role_value_vs_market_reference == pytest.approx(
        -seller_track.average_role_value_vs_market_reference
    )
    assert buyer_summary.roles == ("buyer",)
    assert buyer_summary.role_coverage == 0.5
    assert buyer_summary.unique_run_count == 3
    assert buyer_summary.role_appearance_count == 3
    assert buyer_summary.buyer_average_score == buyer_track.average_score
    assert buyer_summary.seller_average_score is None
    assert buyer_summary.balanced_average_score is None
    assert seller_summary.roles == ("seller",)
    assert seller_summary.role_coverage == 0.5


def test_leaderboard_prefers_model_metadata_for_participant_ids(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = _write_llm_config(tmp_path, output_dir)

    run_experiment_config(
        config_path,
        llm_factory=RoleAwareFakeLLM,
    )
    run_dir = output_dir / "model_pair-phone_001-no_tools-seed-5"
    manifest = load_manifest(run_dir / "manifest.json")
    summary = build_leaderboard(output_dir)

    assert manifest.models == {
        "buyer": "fake/buyer-model",
        "seller": "fake/seller-model",
    }
    assert summary.runs[0].buyer_participant_id == "fake/buyer-model"
    assert summary.runs[0].seller_participant_id == "fake/seller-model"
    assert _track(summary, "buyer", "fake/buyer-model").run_count == 1
    assert _track(summary, "seller", "fake/seller-model").run_count == 1
    assert _participant(summary, "fake/buyer-model").roles == ("buyer",)
    assert _participant(summary, "fake/seller-model").roles == ("seller",)


def test_leaderboard_reports_balanced_role_coverage_for_shared_participant(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = _write_llm_config(
        tmp_path,
        output_dir,
        buyer_model="fake/shared-model",
        seller_model="fake/shared-model",
    )

    run_experiment_config(
        config_path,
        llm_factory=RoleAwareFakeLLM,
    )
    summary = build_leaderboard(output_dir)
    participant = _participant(summary, "fake/shared-model")
    buyer_track = _track(summary, "buyer", "fake/shared-model")
    seller_track = _track(summary, "seller", "fake/shared-model")

    assert len(summary.participant_summaries) == 1
    assert participant.rank == 1
    assert participant.roles == ("buyer", "seller")
    assert participant.role_coverage == 1.0
    assert participant.unique_run_count == 1
    assert participant.role_appearance_count == 2
    assert participant.buyer_average_score == buyer_track.average_score
    assert participant.seller_average_score == seller_track.average_score
    assert participant.balanced_average_score == participant.average_score
    assert participant.coverage_adjusted_score == participant.average_score


def test_leaderboard_cli_prints_and_writes_summary(tmp_path, capsys):
    output_dir = tmp_path / "runs"
    summary_path = tmp_path / "leaderboard_summary.json"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=output_dir)

    exit_code = main(
        [
            "leaderboard",
            "--input-dir",
            str(output_dir),
            "--output",
            str(summary_path),
        ]
    )
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(summary_path.read_text())

    assert exit_code == 0
    assert stdout_payload["schema_version"] == LEADERBOARD_SCHEMA_VERSION
    assert stdout_payload["run_count"] == 3
    assert "participant_summaries" in stdout_payload
    assert stdout_payload["participant_summaries"][0]["role_coverage"] == 0.5
    assert file_payload["schema_version"] == LEADERBOARD_SCHEMA_VERSION
    assert "participant_summaries" in file_payload
    assert file_payload["role_tracks"][0]["role"] == "buyer"


def test_leaderboard_cli_fails_on_empty_input(tmp_path, capsys):
    exit_code = main(["leaderboard", "--input-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "no benchmark run artifacts found" in payload["error"]


def test_build_leaderboard_rejects_duplicate_run_ids(tmp_path):
    output_dir = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=output_dir)
    source = next(
        path for path in output_dir.iterdir() if (path / "manifest.json").exists()
    )
    shutil.copytree(source, output_dir / "duplicate_run_copy")

    with pytest.raises(ValueError, match="duplicate benchmark run_id"):
        build_leaderboard(output_dir)


def _track(summary, role, participant_id):
    for entry in summary.role_tracks:
        if entry.role == role and entry.participant_id == participant_id:
            return entry
    raise AssertionError(f"missing {role} track for {participant_id}")


def _participant(summary, participant_id):
    for entry in summary.participant_summaries:
        if entry.participant_id == participant_id:
            return entry
    raise AssertionError(f"missing participant summary for {participant_id}")


def _write_llm_config(
    tmp_path,
    output_dir,
    *,
    buyer_model="fake/buyer-model",
    seller_model="fake/seller-model",
):
    products_path = tmp_path / "products.json"
    products_path.write_text(
        json.dumps(
            [
                {
                    "id": "phone_001",
                    "name": "Apple iPhone 14 Pro 128GB Unlocked",
                    "description": "Used phone.",
                    "condition": "used_good",
                    "asking_price": 610.0,
                    "synthetic_seller_reservation_price": 520.0,
                    "market_reference": {
                        "reference_price": 575.0,
                        "p25_price": 540.0,
                        "p75_price": 610.0,
                        "sample_size": 24,
                    },
                }
            ],
            indent=2,
        )
        + "\n"
    )
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "model_pair",
        "output_dir": str(output_dir),
        "resume": False,
        "fail_fast": True,
        "seeds": [5],
        "agents": {
            "buyer": {
                "kind": "llm_buyer",
                "params": {
                    "model": buyer_model,
                    "name": "llm_buyer:fake",
                },
            },
            "seller": {
                "kind": "llm_seller",
                "params": {
                    "model": seller_model,
                    "name": "llm_seller:fake",
                },
            },
        },
        "scenarios": [
            {
                "id": "phone_001",
                "products_file": str(products_path),
                "product_index": 0,
                "max_turns": 4,
            }
        ],
        "tool_regimes": [{"id": "no_tools", "tools": []}],
    }
    config_path = tmp_path / "llm_config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    return config_path
