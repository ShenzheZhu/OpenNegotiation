"""Shared helpers for OpenNegotiation CLI commands."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from opennego.model_demo import make_litellm_gateway as _make_litellm_gateway
from opennego.schema import Product


def make_litellm_gateway():
    """Create the default LiteLLM gateway.

    Kept as a module-level indirection so tests can substitute a fake gateway
    by patching ``opennego.cli.common.make_litellm_gateway``.
    """

    return _make_litellm_gateway()


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2))


def print_error(exc: object) -> int:
    """Print a structured CLI error and return the conventional exit code."""

    print_json({"error": str(exc)})
    return 2


def load_first_product(path: str | Path) -> Product:
    records = json.loads(Path(path).read_text())
    if not records:
        raise ValueError(f"No products found in {path}")
    return Product.from_mapping(records[0])


def llm_preflight_error(models: tuple[str, ...]) -> str | None:
    """Check LiteLLM availability and provider credentials before live runs."""

    if importlib.util.find_spec("litellm") is None:
        return (
            "LiteLLM is not installed. Install optional dependencies with: "
            "python -m pip install -e '.[llm]'"
        )

    missing = []
    if any(model.startswith("openrouter/") for model in models):
        if not os.environ.get("OPENROUTER_API_KEY"):
            missing.append("OPENROUTER_API_KEY")
    if any(model.startswith("openai/") for model in models):
        if not os.environ.get("OPENAI_API_KEY"):
            missing.append("OPENAI_API_KEY")
    if any(model.startswith("anthropic/") for model in models):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            missing.append("ANTHROPIC_API_KEY")

    if missing:
        return "Missing provider environment variable(s): " + ", ".join(sorted(set(missing)))
    return None
