"""Serve command: launch the local web client."""

from __future__ import annotations

import argparse


def serve_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch the local OpenNegotiation web client."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    parser.add_argument(
        "--data-dir",
        default="runs/serve",
        help="Directory for agents, runs, lineage, and the rating store.",
    )
    parser.add_argument(
        "--config",
        default="configs/real_market_demo.yaml",
        help="Experiment config used for matches.",
    )
    args = parser.parse_args(argv)

    from opennego.serve.app import run_server

    run_server(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        config_path=args.config,
    )
    return 0
