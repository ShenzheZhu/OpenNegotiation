import json
import textwrap
from pathlib import Path

import opennego.cli as cli_module
from opennego.artifacts import load_manifest
from opennego.cli import main
from opennego.ports import LLMRequest, LLMResponse


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("FakeLLM received more requests than expected")
        return LLMResponse(model=request.model, content=self.responses.pop(0))


def test_run_cli_loads_local_agent_factory(tmp_path):
    output_dir = tmp_path / "runs"
    config_path = _write_runner_config(tmp_path, output_dir)
    module_path = _write_agent_module(tmp_path)

    exit_code = main(
        [
            "run",
            "--config",
            str(config_path),
            "--agent-factory",
            f"external_buyer={module_path}:make_agent",
        ]
    )

    run_dir = output_dir / "cli_agent_loading-camera_001-no_tools-seed-3"
    manifest = load_manifest(run_dir / "manifest.json")
    assert exit_code == 0
    assert manifest.agents["buyer"] == {
        "kind": "external_buyer",
        "name": "cli_runner_buyer",
    }


def test_run_cli_rejects_missing_agent_module_before_output(tmp_path, capsys):
    output_dir = tmp_path / "runs"
    config_path = _write_runner_config(tmp_path, output_dir)

    exit_code = main(
        [
            "run",
            "--config",
            str(config_path),
            "--agent-factory",
            f"external_buyer={tmp_path / 'missing.py'}:make_agent",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "agent module does not exist" in payload["error"]
    assert not output_dir.exists()


def test_spar_cli_loads_local_user_agent_factory(tmp_path):
    output_dir = tmp_path / "sparring"
    module_path = _write_agent_module(tmp_path)

    exit_code = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
            "--user-agent-factory",
            f"{module_path}:make_agent",
            "--user-agent-kind",
            "external_buyer",
            "--user-agent-param",
            "name=cli_spar_buyer",
            "--user-agent-param",
            "offer_price=620",
        ]
    )
    summary = json.loads((output_dir / "sparring_suite.json").read_text())
    learning_dir = Path(summary["results"][0]["learning_input_dir"])
    manifest = load_manifest(learning_dir / "manifest.json")

    assert exit_code == 0
    assert summary["completed"] == 1
    assert summary["user_agent_kind"] == "external_buyer"
    assert manifest.agents["buyer"]["kind"] == "external_buyer"
    assert manifest.agents["buyer"]["name"] == "cli_spar_buyer"
    assert manifest.agents["buyer"]["role"] == "buyer"


def test_spar_cli_rejects_user_agent_params_without_factory(tmp_path, capsys):
    output_dir = tmp_path / "sparring"

    exit_code = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
            "--user-agent-param",
            "name=cli_spar_buyer",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "--user-agent-param requires --user-agent-factory" in payload["error"]
    assert not output_dir.exists()


def test_spar_cli_rejects_profile_llm_without_explicit_profile(tmp_path, capsys):
    output_dir = tmp_path / "sparring"

    exit_code = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-llm-model",
            "openrouter/fake/profile-seller",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "--opponent-llm-model requires at least one --opponent-profile" in (
        payload["error"]
    )
    assert not output_dir.exists()


def test_spar_cli_rejects_profile_llm_missing_provider_key(
    tmp_path,
    capsys,
    monkeypatch,
):
    output_dir = tmp_path / "sparring"
    _pretend_litellm_is_installed(monkeypatch)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    exit_code = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
            "--opponent-llm-model",
            "openrouter/fake/profile-seller",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["error"] == (
        "Missing provider environment variable(s): OPENROUTER_API_KEY"
    )
    assert not output_dir.exists()


def test_spar_cli_runs_profile_llm_opponent_with_fake_gateway(
    tmp_path,
    monkeypatch,
):
    output_dir = tmp_path / "sparring"
    config_path = _write_sparring_config(tmp_path, output_dir)
    fake_llm = FakeLLM(
        ['{"type": "offer", "price": 790, "note": "Profile LLM counteroffer."}']
    )
    _pretend_litellm_is_installed(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr(cli_module, "make_litellm_gateway", lambda: fake_llm)

    exit_code = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
            "--opponent-llm-model",
            "openrouter/fake/profile-seller",
            "--opponent-llm-max-tokens",
            "128",
        ]
    )
    summary = json.loads((output_dir / "sparring_suite.json").read_text())
    learning_dir = Path(summary["results"][0]["learning_input_dir"])
    manifest = load_manifest(learning_dir / "manifest.json")

    assert exit_code == 0
    assert summary["completed"] == 1
    assert summary["opponent_agent_kind"] == (
        "litellm_profile_npc:openrouter/fake/profile-seller"
    )
    assert manifest.agents["seller"]["kind"] == (
        "litellm_profile_npc:openrouter/fake/profile-seller"
    )
    assert manifest.agents["seller"]["profile_id"] == "seller_hardline_anchor_v1"
    assert len(fake_llm.requests) == 1
    assert fake_llm.requests[0].model == "openrouter/fake/profile-seller"
    assert fake_llm.requests[0].max_tokens == 128
    assert fake_llm.requests[0].metadata["agent_role"] == "seller"


def _write_runner_config(tmp_path: Path, output_dir: Path) -> Path:
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "cli_agent_loading",
        "output_dir": str(output_dir),
        "resume": False,
        "fail_fast": True,
        "seeds": [3],
        "agents": {
            "buyer": {
                "kind": "external_buyer",
                "params": {"name": "cli_runner_buyer", "offer_price": 760},
            },
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": [
            {
                "id": "camera_001",
                "products_file": "examples/data/products.json",
                "product_index": 0,
                "max_turns": 4,
            }
        ],
        "tool_regimes": [{"id": "no_tools", "tools": []}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path


def _write_sparring_config(tmp_path: Path, output_dir: Path) -> Path:
    config = {
        "schema_version": "opennego.experiment.v1",
        "name": "cli_profile_llm_sparring",
        "output_dir": str(output_dir / "benchmark"),
        "resume": False,
        "fail_fast": True,
        "seeds": [3],
        "agents": {
            "buyer": {"kind": "tool_aware_buyer"},
            "seller": {"kind": "scripted_seller"},
        },
        "scenarios": [
            {
                "id": "camera_001",
                "products_file": "examples/data/products.json",
                "product_index": 0,
                "max_turns": 2,
            }
        ],
        "tool_regimes": [{"id": "no_tools", "tools": []}],
    }
    path = tmp_path / "sparring_config.json"
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path


def _pretend_litellm_is_installed(monkeypatch):
    real_find_spec = cli_module.importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "litellm":
            return object()
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(cli_module.importlib.util, "find_spec", fake_find_spec)


def _write_agent_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "local_agents.py"
    module_path.write_text(
        textwrap.dedent(
            """
            from dataclasses import dataclass

            from opennego.schema import AgentAction, Role


            @dataclass
            class FixedBuyer:
                role = Role.BUYER
                name: str
                offer_price: float

                def act(self, context):
                    return AgentAction.offer_price(
                        self.offer_price,
                        f"External buyer offers ${self.offer_price:.2f}.",
                    )


            def make_agent(role, params):
                if role != Role.BUYER:
                    raise ValueError("external buyer requires buyer role")
                return FixedBuyer(
                    name=str(params.get("name", "cli_buyer")),
                    offer_price=float(params.get("offer_price", 760)),
                )
            """
        ).strip()
        + "\n"
    )
    return module_path
