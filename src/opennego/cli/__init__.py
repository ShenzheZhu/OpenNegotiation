"""Command-line entry points for OpenNegotiation.

The CLI is a flat command registry. Each command lives in a focused module:

- ``benchmark``: config-driven runs, reports, leaderboards, and role tracks.
- ``demo``: one-command local demo, bundle validation, and live model demo.
- ``learning``: sparring, policy learning, strategy evolution, and training.
- ``market``: market source policies, sold-comps ingestion, and validation.
- ``marketplace``: strategy marketplace profile export and validation.
- ``smoke``: the default deterministic no-key smoke run.
"""

from __future__ import annotations

import sys
from typing import Callable

from . import benchmark, demo, learning, market, marketplace, scenarios, serve, smoke

CommandMain = Callable[[list[str]], int]

# (name, handler, help) grouped by surface; order drives `opennego help` output.
COMMAND_GROUPS: tuple[tuple[str, tuple[tuple[str, CommandMain, str], ...]], ...] = (
    (
        "Benchmark",
        (
            ("run", benchmark.run_main, "Run a config-driven experiment."),
            ("report", benchmark.report_main, "Render run artifacts into an HTML report."),
            ("leaderboard", benchmark.leaderboard_main, "Aggregate runs into leaderboard JSON."),
            ("role-swap", benchmark.role_swap_main, "Run a role-swapped benchmark track."),
            ("arena-plan", benchmark.arena_plan_main, "Plan a reciprocal arena schedule."),
            ("arena-run", benchmark.arena_run_main, "Execute an arena plan into a rating store."),
        ),
    ),
    (
        "Demo",
        (
            ("demo", demo.demo_main, "Generate the complete local demo bundle."),
            ("validate-demo", demo.validate_demo_main, "Validate a demo bundle manifest."),
            ("run-models", demo.run_models_main, "Run a small live-model demo via LiteLLM."),
        ),
    ),
    (
        "Client",
        (
            ("serve", serve.serve_main, "Launch the local web client."),
        ),
    ),
    (
        "Sparring and learning",
        (
            ("strategies", learning.strategies_main, "List NPC strategy profiles."),
            ("spar", learning.spar_main, "Run a sparring suite against NPC profiles."),
            ("learn", learning.learn_main, "Generate a battle report from run artifacts."),
            ("evolve", learning.evolve_main, "Derive a strategy candidate from a battle report."),
            ("compare", learning.compare_main, "Compare before/after battle reports."),
            ("train", learning.train_main, "Run the full sparring/patch/rerun training loop."),
            ("apply-strategy", learning.apply_strategy_main, "Apply a candidate into a strategy config."),
            ("lineage", learning.lineage_main, "Print and validate a strategy evolution lineage."),
            (
                "export-training-adapter",
                learning.export_training_adapter_main,
                "Export a strategy config as an external adapter package.",
            ),
            (
                "validate-training-adapter",
                learning.validate_training_adapter_main,
                "Validate an external training adapter package.",
            ),
        ),
    ),
    (
        "Market data",
        (
            ("market-source-policy", market.market_source_policy_main, "Write a market source policy gate."),
            ("validate-market-source", market.validate_market_source_main, "Validate a source policy artifact."),
            ("ingest-market", market.ingest_market_main, "Normalize offline sold-comps exports."),
            ("ingest-ebay", market.ingest_ebay_main, "Ingest eBay Marketplace Insights sold comps."),
            ("ingest-ebay-active", market.ingest_ebay_active_main, "Ingest eBay Browse active listings."),
            ("validate-market", market.validate_market_main, "Validate normalized market fixtures."),
            ("scenarios", scenarios.scenarios_main, "Build and validate scenario packs."),
        ),
    ),
    (
        "Strategy marketplace",
        (
            ("marketplace-export", marketplace.marketplace_export_main, "Export a candidate as a profile."),
            ("validate-marketplace", marketplace.validate_marketplace_main, "Validate registry and profiles."),
        ),
    ),
)

COMMANDS: dict[str, CommandMain] = {
    name: handler
    for _, group in COMMAND_GROUPS
    for name, handler, _ in group
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        command = COMMANDS.get(argv[0])
        if command is not None:
            return command(argv[1:])
        if argv[0] == "help":
            print(_usage())
            return 0
    # No recognized command: run the deterministic smoke demo. This keeps
    # `opennego` and `python -m opennego.cli` usable without arguments.
    return smoke.smoke_main(argv)


def _usage() -> str:
    lines = [
        "usage: opennego <command> [options]",
        "",
        "Run `opennego <command> --help` for command options.",
        "Without a command, opennego runs the deterministic smoke demo.",
    ]
    for group_name, group in COMMAND_GROUPS:
        lines.append("")
        lines.append(f"{group_name}:")
        for name, _, help_text in group:
            lines.append(f"  {name:<26} {help_text}")
    return "\n".join(lines)


__all__ = ["COMMANDS", "COMMAND_GROUPS", "main"]
