"""Co-evolution CLI, report, and BYOK agent-factory seam (#231)."""

import json

from opennego.coevolution import (
    COEVOLUTION_SCHEMA_VERSION,
    build_agent,
    render_coevolution_report,
    run_coevolution,
)


def test_coevolve_cli_runs_and_writes_report(tmp_path, capsys):
    from opennego.cli import COMMANDS
    from opennego.cli.learning import coevolve_main

    assert "coevolve" in COMMANDS

    report = tmp_path / "coevo.html"
    rc = coevolve_main(
        [
            "--output-dir",
            str(tmp_path / "c"),
            "--generations",
            "3",
            "--population",
            "4",
            "--scenario-count",
            "1",
            "--evolve",
            "buyer",
            "--report",
            str(report),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == COEVOLUTION_SCHEMA_VERSION
    assert payload["evolve_roles"] == ["buyer"]
    assert payload["report"] == str(report)
    html = report.read_text()
    assert "Co-evolution run" in html and "Champion lineage" in html


def test_agent_factory_seam_is_used(tmp_path):
    # The BYOK layer plugs in by supplying its own factory; the engine must call
    # it for every genome instead of build_agent.
    calls = {"n": 0}

    def counting_factory(genome):
        calls["n"] += 1
        return build_agent(genome)

    result = run_coevolution(
        output_dir=tmp_path / "c",
        generations=2,
        population=4,
        scenario_count=1,
        seed=5,
        agent_factory=counting_factory,
    )
    assert result.schema_version == COEVOLUTION_SCHEMA_VERSION
    # 4 buyers + 4 sellers built per generation, 2 generations.
    assert calls["n"] == (4 + 4) * 2


def test_report_renders_from_result(tmp_path):
    result = run_coevolution(
        output_dir=tmp_path / "c", generations=2, population=4, scenario_count=1, seed=1
    )
    html = render_coevolution_report(result)
    assert result.buyer_champion.genome_id in html
    assert result.seller_champion.genome_id in html
