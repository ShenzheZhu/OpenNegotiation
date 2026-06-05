"""Explicit local Python agent factory loading for CLI entry points."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from opennego.ports import AgentPort
from opennego.schema import Role

AgentFactory = Callable[[Role, Mapping[str, Any]], AgentPort]
SparringUserAgentFactory = Callable[[Role], AgentPort]


class AgentLoadError(ValueError):
    """Raised when a user-supplied local agent factory cannot be loaded."""


def load_agent_factories(specs: Sequence[str]) -> Mapping[str, AgentFactory]:
    """Load config-runner factories from KIND=PATH:CALLABLE specs."""

    factories: dict[str, AgentFactory] = {}
    for spec in specs:
        kind, target = _split_kind_target(spec)
        if kind in factories:
            raise AgentLoadError(f"duplicate agent factory kind {kind!r}")
        factories[kind] = load_agent_factory(target)
    return factories


def load_agent_factory(target: str) -> AgentFactory:
    """Load a factory callable from an explicit local PATH:CALLABLE target."""

    module_path, attribute = _split_target(target)
    module = _load_module(module_path)
    try:
        value = getattr(module, attribute)
    except AttributeError as exc:
        raise AgentLoadError(
            f"{module_path}: callable {attribute!r} was not found"
        ) from exc
    if not callable(value):
        raise AgentLoadError(f"{module_path}: {attribute!r} is not callable")
    return value


def load_sparring_user_agent_factory(
    target: str,
    *,
    params: Mapping[str, Any] | None = None,
) -> SparringUserAgentFactory:
    """Adapt a local (role, params) factory to sparring's role-only callable."""

    factory = load_agent_factory(target)
    bound_params = dict(params or {})

    def create(role: Role) -> AgentPort:
        return factory(role, bound_params)

    return create


def parse_agent_params(values: Sequence[str]) -> Mapping[str, Any]:
    """Parse KEY=VALUE CLI params, using JSON scalars when possible."""

    params: dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise AgentLoadError(
                f"agent param {item!r}: expected KEY=VALUE"
            )
        key, raw_value = item.split("=", 1)
        if not key:
            raise AgentLoadError(f"agent param {item!r}: key cannot be empty")
        params[key] = _parse_param_value(raw_value)
    return params


def _split_kind_target(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        raise AgentLoadError(
            f"agent factory spec {spec!r}: expected KIND=PATH:CALLABLE"
        )
    kind, target = spec.split("=", 1)
    if not kind:
        raise AgentLoadError(f"agent factory spec {spec!r}: kind cannot be empty")
    if not target:
        raise AgentLoadError(f"agent factory spec {spec!r}: target cannot be empty")
    return kind, target


def _split_target(target: str) -> tuple[Path, str]:
    if ":" not in target:
        raise AgentLoadError(
            f"agent factory target {target!r}: expected PATH:CALLABLE"
        )
    path_text, attribute = target.rsplit(":", 1)
    if not path_text:
        raise AgentLoadError(f"agent factory target {target!r}: path cannot be empty")
    if not attribute:
        raise AgentLoadError(
            f"agent factory target {target!r}: callable cannot be empty"
        )
    path = Path(path_text).expanduser()
    if not path.exists():
        raise AgentLoadError(f"{path}: agent module does not exist")
    if not path.is_file():
        raise AgentLoadError(f"{path}: agent module path is not a file")
    return path, attribute


def _load_module(path: Path):
    resolved = path.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    module_name = f"_opennego_user_agent_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise AgentLoadError(f"{path}: could not create import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise AgentLoadError(f"{path}: failed to import agent module: {exc}") from exc
    return module


def _parse_param_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
