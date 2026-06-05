import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from opennego.artifacts import load_manifest, load_metric_report
from opennego.ports import LLMRequest, LLMResponse
from opennego.runner import ConfigValidationError, run_experiment_config
from opennego.schema import AgentAction, AgentContext, Role


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


def test_config_runner_accepts_registered_custom_agent(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(tmp_path, output_dir)
    config = read_config(config_path)
    config["agents"]["buyer"] = {
        "kind": "fixed_offer_buyer",
        "params": {"name": "external_test_buyer", "offer_price": 760},
    }
    config["tool_regimes"] = [{"id": "no_tools", "tools": []}]
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    summary = run_experiment_config(
        config_path,
        agent_factories={"fixed_offer_buyer": fixed_offer_buyer_factory},
    )

    assert summary.completed == 1
    assert summary.failed == 0
    run_dir = output_dir / "runner_smoke-camera_001-no_tools-seed-11"
    manifest = load_manifest(run_dir / "manifest.json")
    metrics = load_metric_report(run_dir / "metrics.json")
    assert manifest.agents["buyer"]["kind"] == "fixed_offer_buyer"
    assert manifest.agents["buyer"]["name"] == "external_test_buyer"
    assert metrics.outcome == "deal"
    assert metrics.deal_price == 760.0


def test_config_runner_rejects_wrong_role_custom_agent_before_output(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(tmp_path, output_dir)
    config = read_config(config_path)
    config["agents"]["buyer"] = {"kind": "wrong_role_agent"}
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    with pytest.raises(ConfigValidationError, match="expected 'buyer'"):
        run_experiment_config(
            config_path,
            agent_factories={"wrong_role_agent": wrong_role_agent_factory},
        )

    assert not output_dir.exists()


def test_config_runner_accepts_llm_agents_with_injected_llm_factory(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(tmp_path, output_dir)
    config = read_config(config_path)
    config["agents"] = {
        "buyer": {
            "kind": "llm_buyer",
            "params": {
                "model": "fake/buyer-model",
                "name": "llm_buyer:fake",
                "tool_policy": "none",
                "temperature": 0.1,
                "max_tokens": 64,
            },
        },
        "seller": {
            "kind": "llm_seller",
            "params": {
                "model": "fake/seller-model",
                "name": "llm_seller:fake",
            },
        },
    }
    config["tool_regimes"] = [{"id": "no_tools", "tools": []}]
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    llm_factory = TrackingLLMFactory()

    summary = run_experiment_config(config_path, llm_factory=llm_factory)

    run_dir = output_dir / "runner_smoke-camera_001-no_tools-seed-11"
    manifest = load_manifest(run_dir / "manifest.json")
    metrics = load_metric_report(run_dir / "metrics.json")
    assert summary.completed == 1
    assert summary.failed == 0
    assert manifest.agents["buyer"] == {
        "name": "llm_buyer:fake",
        "kind": "llm_buyer",
    }
    assert manifest.agents["seller"] == {
        "name": "llm_seller:fake",
        "kind": "llm_seller",
    }
    assert manifest.models == {
        "buyer": "fake/buyer-model",
        "seller": "fake/seller-model",
    }
    assert metrics.outcome == "deal"
    assert metrics.deal_price == 760.0
    assert [request.metadata["agent_role"] for request in llm_factory.requests] == [
        "buyer",
        "seller",
    ]


def test_config_runner_rejects_llm_agent_without_llm_factory_before_output(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(tmp_path, output_dir)
    config = read_config(config_path)
    config["agents"]["buyer"] = {
        "kind": "llm_buyer",
        "params": {"model": "fake/buyer-model"},
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    with pytest.raises(ConfigValidationError, match="llm_buyer requires llm_factory"):
        run_experiment_config(config_path)

    assert not output_dir.exists()


def test_config_runner_rejects_llm_agent_missing_model_before_output(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = write_config(tmp_path, output_dir)
    config = read_config(config_path)
    config["agents"]["buyer"] = {"kind": "llm_buyer", "params": {}}
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    with pytest.raises(ConfigValidationError, match="llm_buyer.params.model"):
        run_experiment_config(config_path)

    assert not output_dir.exists()


@dataclass
class FixedOfferBuyer:
    name: str
    offer_price: float
    role: Role = Role.BUYER

    def act(self, context: AgentContext) -> AgentAction:
        return AgentAction.offer_price(
            self.offer_price,
            f"My offer is ${self.offer_price:.2f}.",
        )


@dataclass
class WrongRoleAgent:
    name: str = "wrong_role_agent"
    role: Role = Role.SELLER

    def act(self, context: AgentContext) -> AgentAction:
        return AgentAction.reject("Wrong role.")


def fixed_offer_buyer_factory(role, params):
    return FixedOfferBuyer(
        name=str(params.get("name", "fixed_offer_buyer")),
        offer_price=float(params.get("offer_price", 760)),
    )


def wrong_role_agent_factory(role, params):
    return WrongRoleAgent()


class TrackingLLMFactory:
    def __init__(self):
        self.requests = []

    def __call__(self):
        return FakeRunnerLLM(self.requests)


class FakeRunnerLLM:
    def __init__(self, requests):
        self.requests = requests

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if request.metadata["agent_role"] == "buyer":
            return LLMResponse(
                model=request.model,
                content=(
                    '{"type": "offer", "content": null, "price": 760, '
                    '"note": "Config runner LLM offer.", "tool": null}'
                ),
            )
        return LLMResponse(
            model=request.model,
            content=(
                '{"type": "accept", "content": "Accepted.", "price": null, '
                '"note": "Config runner LLM accepts.", "tool": null}'
            ),
        )
