import json
import textwrap
from pathlib import Path

from opennego.artifacts import load_manifest
from opennego.cli import main


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
