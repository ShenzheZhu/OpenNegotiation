"""Benchmark commands: config runs, reports, leaderboards, and role tracks."""

from __future__ import annotations

import argparse
from pathlib import Path

from opennego.agent_loader import AgentLoadError, load_agent_factories
from opennego.arena import ArenaPlanError, write_arena_plan
from opennego.artifacts import to_jsonable
from opennego.leaderboard import build_leaderboard, write_leaderboard
from opennego.report import write_demo_report
from opennego.role_swap import run_role_swap_benchmark
from opennego.runner import (
    ConfigValidationError,
    LLM_AGENT_KINDS,
    load_experiment_config,
    run_experiment_config,
)

from . import common


def run_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a config-driven OpenNegotiation experiment."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an OpenNegotiation experiment config.",
    )
    parser.add_argument("--output-dir", help="Override the config output_dir.")
    parser.add_argument("--resume", dest="resume", action="store_true", default=None)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument(
        "--agent-factory",
        action="append",
        default=[],
        metavar="KIND=PATH:CALLABLE",
        help=(
            "Load a local AgentPort factory for a config agent kind. "
            "May be provided multiple times."
        ),
    )
    args = parser.parse_args(argv)

    try:
        agent_factories = load_agent_factories(args.agent_factory)
        llm_models = _config_llm_models(args.config)
        llm_factory = None
        if llm_models is not None:
            preflight_error = (
                common.llm_preflight_error(llm_models) if llm_models else None
            )
            if preflight_error is not None:
                return common.print_error(preflight_error)
            llm_factory = common.make_litellm_gateway
        summary = run_experiment_config(
            args.config,
            resume=args.resume,
            output_dir=args.output_dir,
            agent_factories=agent_factories,
            llm_factory=llm_factory,
        )
    except (AgentLoadError, ConfigValidationError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(summary))
    return 1 if summary.failed else 0


def _config_llm_models(config_path: str | Path) -> tuple[str, ...] | None:
    config = load_experiment_config(config_path)
    models: list[str] = []
    has_llm_agent = False
    for spec in (config.agents.buyer, config.agents.seller):
        if spec.kind in LLM_AGENT_KINDS:
            has_llm_agent = True
            model = spec.params.get("model")
            if isinstance(model, str) and model:
                models.append(model)
    return tuple(models) if has_llm_agent else None


def report_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an OpenNegotiation demo HTML report."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing one run artifact or multiple run artifact subdirectories.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the HTML report to write.",
    )
    args = parser.parse_args(argv)

    try:
        output_path = write_demo_report(args.input_dir, args.output)
    except ValueError as exc:
        return common.print_error(exc)

    common.print_json({"report": str(output_path)})
    return 0


def leaderboard_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark artifacts into leaderboard JSON."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing benchmark run artifact subdirectories.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write leaderboard_summary.json.",
    )
    args = parser.parse_args(argv)

    try:
        summary = build_leaderboard(args.input_dir)
        if args.output:
            write_leaderboard(args.input_dir, args.output)
    except (OSError, ValueError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(summary))
    return 0


def arena_plan_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a reciprocal arena planning artifact without running it."
    )
    parser.add_argument(
        "--participant",
        action="append",
        dest="participants",
        required=True,
        help="Participant id to include. Provide at least two.",
    )
    parser.add_argument(
        "--scenario-id",
        action="append",
        dest="scenario_ids",
        help="Scenario id to schedule. Defaults to real_market_demo.",
    )
    parser.add_argument(
        "--seed",
        action="append",
        dest="seeds",
        type=int,
        help="Seed to schedule. Defaults to 13.",
    )
    parser.add_argument(
        "--include-self-play",
        action="store_true",
        help="Include diagnostic self-play rows. These should not drive rankings.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write opennego.arena_plan.v1 JSON.",
    )
    args = parser.parse_args(argv)

    try:
        plan = write_arena_plan(
            args.output,
            participants=tuple(args.participants or ()),
            scenario_ids=tuple(args.scenario_ids or ("real_market_demo",)),
            seeds=tuple(args.seeds or (13,)),
            include_self_play=args.include_self_play,
        )
    except (OSError, ArenaPlanError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(plan))
    return 0


def role_swap_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a small no-key role-swapped benchmark track."
    )
    parser.add_argument(
        "--output-dir",
        default="runs/role_swap",
        help="Directory for role-specific runs and combined leaderboard artifacts.",
    )
    parser.add_argument(
        "--config",
        default="configs/real_market_demo.yaml",
        help="Base experiment config whose scenario and transaction settings are reused.",
    )
    parser.add_argument(
        "--participant-id",
        default="baseline_strategy",
        help="Stable strategy identity evaluated as both buyer and seller.",
    )
    args = parser.parse_args(argv)

    try:
        summary = run_role_swap_benchmark(
            output_dir=args.output_dir,
            config_path=args.config,
            participant_id=args.participant_id,
        )
    except (OSError, ValueError, ConfigValidationError) as exc:
        return common.print_error(exc)

    common.print_json(to_jsonable(summary))
    return 0 if summary.status == "completed" else 1
