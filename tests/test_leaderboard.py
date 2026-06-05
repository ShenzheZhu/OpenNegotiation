import json

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

    assert summary.schema_version == LEADERBOARD_SCHEMA_VERSION
    assert summary.run_count == 3
    assert len(summary.runs) == 3
    assert [row.rank for row in summary.runs] == [1, 2, 3]
    assert all(row.score > 0 for row in summary.runs)
    assert buyer_track.rank == 1
    assert buyer_track.run_count == 3
    assert buyer_track.deal_rate == 1.0
    assert seller_track.run_count == 3
    assert buyer_track.average_role_value_vs_market_reference == pytest.approx(
        -seller_track.average_role_value_vs_market_reference
    )


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
    assert file_payload["schema_version"] == LEADERBOARD_SCHEMA_VERSION
    assert file_payload["role_tracks"][0]["role"] == "buyer"


def test_leaderboard_cli_fails_on_empty_input(tmp_path, capsys):
    exit_code = main(["leaderboard", "--input-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "no benchmark run artifacts found" in payload["error"]


def _track(summary, role, participant_id):
    for entry in summary.role_tracks:
        if entry.role == role and entry.participant_id == participant_id:
            return entry
    raise AssertionError(f"missing {role} track for {participant_id}")


def _write_llm_config(tmp_path, output_dir):
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
                    "model": "fake/buyer-model",
                    "name": "llm_buyer:fake",
                },
            },
            "seller": {
                "kind": "llm_seller",
                "params": {
                    "model": "fake/seller-model",
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
