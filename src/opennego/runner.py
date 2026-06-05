"""Config-driven experiment runner for OpenNegotiation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from opennego.agents import (
    ScriptedSeller,
    ToolAwareBuyer,
    make_llm_buyer,
    make_llm_seller,
)
from opennego.artifacts import (
    ArtifactValidationError,
    load_manifest,
    load_metric_report,
    load_scenario_artifact,
    load_trace,
    write_run_artifacts,
)
from opennego.environment import NegotiationEnvironment
from opennego.environment import ToolRuntimeConfig
from opennego.ports import AgentPort, LLMPort, ToolPort
from opennego.schema import Product, Role, Scenario
from opennego.tools import MarketPriceTool
from opennego.transactions import FixtureTransactionSimulator

EXPERIMENT_CONFIG_VERSION = "opennego.experiment.v1"


class ConfigValidationError(ValueError):
    """Raised when an experiment config is malformed."""


AgentFactory = Callable[[Role, Mapping[str, Any]], AgentPort]
LLMFactory = Callable[[], LLMPort]
LLM_AGENT_KINDS = frozenset({"llm_buyer", "llm_seller"})
RESERVED_AGENT_PARAMS = frozenset({"participant_id"})


@dataclass(frozen=True)
class AgentSpecConfig:
    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentPairConfig:
    buyer: AgentSpecConfig
    seller: AgentSpecConfig

    @property
    def buyer_kind(self) -> str:
        return self.buyer.kind

    @property
    def seller_kind(self) -> str:
        return self.seller.kind


@dataclass(frozen=True)
class ScenarioConfig:
    id: str | None
    products_file: Path
    product_id: str | None = None
    product_index: int = 0
    buyer_budget: float | None = None
    seller_reservation_price: float | None = None
    max_turns: int = 8
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str
    source: Path | None = None
    visibility: str = "private"
    roles: tuple[Role, ...] | None = None
    mode: str = "clean"
    fail_fast: bool = False
    enabled: bool = True
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ToolRegimeConfig:
    id: str
    tools: tuple[ToolSpec, ...] = ()
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    output_dir: Path
    scenarios: tuple[ScenarioConfig, ...]
    tool_regimes: tuple[ToolRegimeConfig, ...]
    agents: AgentPairConfig
    seeds: tuple[int | None, ...] = (None,)
    resume: bool = False
    fail_fast: bool = True
    transaction: "TransactionConfig | None" = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PreparedRun:
    run_id: str
    output_dir: Path
    scenario_id: str
    scenario: Scenario
    tool_regime: ToolRegimeConfig
    tools: tuple[ToolPort, ...]
    tool_configs: tuple[ToolRuntimeConfig, ...]
    transaction_simulator: FixtureTransactionSimulator | None
    seed: int | None


@dataclass(frozen=True)
class TransactionConfig:
    kind: str = "fixture"
    enabled: bool = False
    shipping_cost: float = 0.0
    tax_rate: float = 0.0
    escrow_fee: float = 0.0
    payment_fee_rate: float = 0.0
    seller_fee_rate: float = 0.0
    return_risk: float = 0.0
    reputation_risk: float = 0.0
    dispute_risk: float = 0.0
    payment_success: bool = True
    shipping_success: bool = True
    item_matches_listing: bool = True
    max_buyer_total_cost: float | None = None
    min_seller_net_revenue: float | None = None
    max_dispute_risk: float | None = None
    return_window_days: int | None = None
    min_return_window_days: int | None = None
    payment_method: str | None = None
    payment_processor: str | None = None
    escrow_release_policy: str | None = None
    shipping_carrier: str | None = None
    shipping_service: str | None = None
    tracking_required: bool = False
    delivery_days: int | None = None
    max_delivery_days: int | None = None
    return_shipping_payer: str | None = None
    inspection_period_days: int | None = None
    warranty_days: int | None = None
    min_warranty_days: int | None = None
    warranty_provider: str | None = None
    compliance_checks: tuple[str, ...] = ()
    compliance_passed: bool = True
    dispute_window_days: int | None = None
    dispute_resolution_policy: str | None = None
    failure_reason: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: str
    output_dir: str
    outcome: str | None = None
    deal_price: float | None = None
    completed_turns: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class ExperimentSummary:
    name: str
    output_dir: str
    total_runs: int
    completed: int
    skipped: int
    failed: int
    runs: tuple[RunRecord, ...]


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Load and validate an experiment config.

    JSON is always supported. YAML files are supported when PyYAML is installed.
    JSON-compatible YAML also works through the standard JSON parser, which keeps
    the no-key smoke config dependency-free.
    """

    config_path = Path(path)
    data = _read_config_mapping(config_path)
    version = data.get("schema_version")
    if version != EXPERIMENT_CONFIG_VERSION:
        raise ConfigValidationError(
            f"schema_version: expected {EXPERIMENT_CONFIG_VERSION!r}, got {version!r}"
        )

    name = _required_str(data, "name")
    output_dir = Path(_required_str(data, "output_dir"))
    scenarios = tuple(
        _parse_scenario(item, index)
        for index, item in enumerate(_required_list(data, "scenarios"))
    )
    if not scenarios:
        raise ConfigValidationError("scenarios: expected at least one scenario")

    tool_regime_items = data.get("tool_regimes", [{"id": "no_tools", "tools": []}])
    if not isinstance(tool_regime_items, list):
        raise ConfigValidationError("tool_regimes: expected list")
    tool_regimes = tuple(
        _parse_tool_regime(item, index)
        for index, item in enumerate(tool_regime_items)
    )
    if not tool_regimes:
        raise ConfigValidationError("tool_regimes: expected at least one regime")

    seeds = _parse_seeds(data.get("seeds", [None]))
    agents = _parse_agents(_required_mapping(data, "agents"))

    resume = _optional_bool(data, "resume", False)
    fail_fast = _optional_bool(data, "fail_fast", True)
    transaction = _parse_transaction_config(data.get("transaction"))
    metadata = _optional_mapping(data, "metadata")
    return ExperimentConfig(
        name=name,
        output_dir=output_dir,
        scenarios=scenarios,
        tool_regimes=tool_regimes,
        agents=agents,
        seeds=seeds,
        resume=resume,
        fail_fast=fail_fast,
        transaction=transaction,
        metadata=metadata,
    )


def run_experiment_config(
    path: str | Path,
    *,
    resume: bool | None = None,
    output_dir: str | Path | None = None,
    agent_factories: Mapping[str, AgentFactory] | None = None,
    llm_factory: LLMFactory | None = None,
) -> ExperimentSummary:
    """Run all jobs declared by an experiment config."""

    config = load_experiment_config(path)
    if resume is not None:
        config = replace(config, resume=resume)
    if output_dir is not None:
        config = replace(config, output_dir=Path(output_dir))

    agent_registry = _agent_factory_registry(
        agent_factories,
        llm_factory=llm_factory,
    )
    _validate_agent_kinds(config.agents, agent_registry)
    prepared_runs = prepare_runs(config)
    records: list[RunRecord] = []
    for prepared_run in prepared_runs:
        if config.resume and _is_completed_run(
            prepared_run.output_dir,
            prepared_run.run_id,
        ):
            records.append(
                RunRecord(
                    run_id=prepared_run.run_id,
                    status="skipped",
                    output_dir=str(prepared_run.output_dir),
                )
            )
            continue

        try:
            result = _execute_prepared_run(prepared_run, config, agent_registry)
        except Exception as exc:  # pragma: no cover - exercised via CLI failure paths
            records.append(
                RunRecord(
                    run_id=prepared_run.run_id,
                    status="failed",
                    output_dir=str(prepared_run.output_dir),
                    error=str(exc),
                )
            )
            if config.fail_fast:
                break
            continue

        records.append(
            RunRecord(
                run_id=prepared_run.run_id,
                status="completed",
                output_dir=str(prepared_run.output_dir),
                outcome=result.outcome,
                deal_price=result.deal_price,
                completed_turns=result.completed_turns,
            )
        )

    return ExperimentSummary(
        name=config.name,
        output_dir=str(config.output_dir),
        total_runs=len(prepared_runs),
        completed=sum(1 for record in records if record.status == "completed"),
        skipped=sum(1 for record in records if record.status == "skipped"),
        failed=sum(1 for record in records if record.status == "failed"),
        runs=tuple(records),
    )


def prepare_runs(config: ExperimentConfig) -> tuple[PreparedRun, ...]:
    """Validate inputs and build all runs before starting execution."""

    prepared_runs: list[PreparedRun] = []
    for scenario_config in config.scenarios:
        scenario = _build_scenario(scenario_config)
        scenario_id = scenario_config.id or scenario.product.id
        for tool_regime in config.tool_regimes:
            tools, tool_configs = _build_tools(tool_regime)
            for seed in config.seeds:
                run_id = _run_id(config.name, scenario_id, tool_regime.id, seed)
                prepared_runs.append(
                    PreparedRun(
                        run_id=run_id,
                        output_dir=config.output_dir / run_id,
                        scenario_id=scenario_id,
                        scenario=scenario,
                        tool_regime=tool_regime,
                        tools=tools,
                        tool_configs=tool_configs,
                        transaction_simulator=_build_transaction_simulator(
                            config.transaction
                        ),
                        seed=seed,
                    )
                )
    _validate_run_ids(prepared_runs)
    return tuple(prepared_runs)


def _execute_prepared_run(
    prepared_run: PreparedRun,
    config: ExperimentConfig,
    agent_registry: Mapping[str, AgentFactory],
):
    buyer, seller = _build_agents(config.agents, agent_registry)
    env = NegotiationEnvironment(
        scenario=prepared_run.scenario,
        buyer=buyer,
        seller=seller,
        tools=prepared_run.tools,
        tool_configs=prepared_run.tool_configs,
        transaction_simulator=prepared_run.transaction_simulator,
    )
    result = env.run()
    write_run_artifacts(
        result=result,
        output_dir=prepared_run.output_dir,
        run_id=prepared_run.run_id,
        scenario_id=prepared_run.scenario_id,
        seed=prepared_run.seed,
        agents={
            "buyer": _agent_manifest(buyer, config.agents.buyer),
            "seller": _agent_manifest(seller, config.agents.seller),
        },
        models=_model_metadata(config.agents),
        tool_regime=_tool_regime_metadata(prepared_run.tool_regime),
        metadata={
            "experiment_name": config.name,
            "transaction": _transaction_metadata(config.transaction),
            **dict(config.metadata or {}),
        },
    )
    return result


def _agent_manifest(agent: AgentPort, spec: AgentSpecConfig) -> dict[str, object]:
    payload: dict[str, object] = {"name": agent.name, "kind": spec.kind}
    participant_id = spec.params.get("participant_id")
    if isinstance(participant_id, str) and participant_id:
        payload["participant_id"] = participant_id
    return payload


def _build_agents(
    config: AgentPairConfig,
    agent_registry: Mapping[str, AgentFactory],
) -> tuple[AgentPort, AgentPort]:
    return (
        _create_agent(config.buyer, Role.BUYER, agent_registry),
        _create_agent(config.seller, Role.SELLER, agent_registry),
    )


def _agent_factory_registry(
    agent_factories: Mapping[str, AgentFactory] | None,
    *,
    llm_factory: LLMFactory | None,
) -> Mapping[str, AgentFactory]:
    registry: dict[str, AgentFactory] = {
        "tool_aware_buyer": _make_tool_aware_buyer,
        "scripted_seller": _make_scripted_seller,
        "llm_buyer": _make_llm_agent_factory(
            kind="llm_buyer",
            expected_role=Role.BUYER,
            llm_factory=llm_factory,
        ),
        "llm_seller": _make_llm_agent_factory(
            kind="llm_seller",
            expected_role=Role.SELLER,
            llm_factory=llm_factory,
        ),
    }
    registry.update(agent_factories or {})
    return registry


def _validate_agent_kinds(
    config: AgentPairConfig,
    agent_registry: Mapping[str, AgentFactory],
) -> None:
    _create_agent(config.buyer, Role.BUYER, agent_registry)
    _create_agent(config.seller, Role.SELLER, agent_registry)


def _create_agent(
    spec: AgentSpecConfig,
    role: Role,
    agent_registry: Mapping[str, AgentFactory],
) -> AgentPort:
    factory = agent_registry.get(spec.kind)
    if factory is None:
        raise ConfigValidationError(
            f"agents.{role.value}.kind: unsupported kind {spec.kind!r}"
        )
    try:
        agent = factory(role, spec.params)
    except ConfigValidationError:
        raise
    except Exception as exc:
        raise ConfigValidationError(
            f"agents.{role.value}.kind {spec.kind!r}: factory failed: {exc}"
        ) from exc
    if getattr(agent, "role", None) != role:
        actual = getattr(agent, "role", None)
        actual_value = actual.value if isinstance(actual, Role) else repr(actual)
        raise ConfigValidationError(
            f"agents.{role.value}.kind {spec.kind!r}: factory returned role "
            f"{actual_value!r}, expected {role.value!r}"
        )
    if not isinstance(getattr(agent, "name", None), str) or not agent.name:
        raise ConfigValidationError(
            f"agents.{role.value}.kind {spec.kind!r}: factory returned agent "
            "without a non-empty string name"
        )
    if not callable(getattr(agent, "act", None)):
        raise ConfigValidationError(
            f"agents.{role.value}.kind {spec.kind!r}: factory returned agent "
            "without callable act(context)"
        )
    return agent


def _make_tool_aware_buyer(role: Role, params: Mapping[str, Any]) -> AgentPort:
    if role != Role.BUYER:
        raise ConfigValidationError("tool_aware_buyer requires buyer role")
    return ToolAwareBuyer(**_agent_kwargs("tool_aware_buyer", params))


def _make_scripted_seller(role: Role, params: Mapping[str, Any]) -> AgentPort:
    if role != Role.SELLER:
        raise ConfigValidationError("scripted_seller requires seller role")
    return ScriptedSeller(**_agent_kwargs("scripted_seller", params))


def _make_llm_agent_factory(
    *,
    kind: str,
    expected_role: Role,
    llm_factory: LLMFactory | None,
) -> AgentFactory:
    def factory(role: Role, params: Mapping[str, Any]) -> AgentPort:
        if role != expected_role:
            raise ConfigValidationError(
                f"{kind} requires {expected_role.value} role"
            )
        model = _param_str(kind, params, "model")
        name = _optional_param_str(kind, params, "name") or kind
        tool_policy = _optional_param_str(kind, params, "tool_policy") or "none"
        temperature = _optional_param_float(kind, params, "temperature", 0.0)
        max_tokens = _optional_param_int(kind, params, "max_tokens", 512)
        if llm_factory is None:
            raise ConfigValidationError(
                f"{kind} requires llm_factory; pass one to run_experiment_config "
                "or use the CLI with LiteLLM dependencies and credentials"
            )
        maker = make_llm_buyer if expected_role == Role.BUYER else make_llm_seller
        return maker(
            llm=llm_factory(),
            model=model,
            name=name,
            tool_policy=tool_policy,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    return factory


def _agent_kwargs(kind: str, params: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return {
            key: value
            for key, value in dict(params).items()
            if key not in RESERVED_AGENT_PARAMS
        }
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(f"{kind}.params: expected object") from exc


def _model_metadata(config: AgentPairConfig) -> Mapping[str, str]:
    models: dict[str, str] = {}
    for role, spec in ((Role.BUYER, config.buyer), (Role.SELLER, config.seller)):
        if spec.kind in LLM_AGENT_KINDS:
            model = spec.params.get("model")
            if isinstance(model, str) and model:
                models[role.value] = model
    return models


def _param_str(kind: str, params: Mapping[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigValidationError(f"{kind}.params.{key}: expected non-empty string")
    return value


def _optional_param_str(
    kind: str,
    params: Mapping[str, Any],
    key: str,
) -> str | None:
    value = params.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigValidationError(f"{kind}.params.{key}: expected string")
    return value


def _optional_param_float(
    kind: str,
    params: Mapping[str, Any],
    key: str,
    default: float,
) -> float:
    value = params.get(key, default)
    if not isinstance(value, (int, float)):
        raise ConfigValidationError(f"{kind}.params.{key}: expected number")
    return float(value)


def _optional_param_int(
    kind: str,
    params: Mapping[str, Any],
    key: str,
    default: int,
) -> int | None:
    value = params.get(key, default)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ConfigValidationError(f"{kind}.params.{key}: expected integer or null")
    return value


def _build_scenario(config: ScenarioConfig) -> Scenario:
    product = _select_product(
        config.products_file,
        config.product_id,
        config.product_index,
    )
    buyer_budget = config.buyer_budget
    if buyer_budget is None:
        buyer_budget = float(
            product.attributes.get("buyer_budget", product.list_price * 0.85)
        )
    seller_reservation_price = config.seller_reservation_price
    if seller_reservation_price is None:
        seller_reservation_price = product.wholesale_price
    return Scenario(
        product=product,
        buyer_budget=buyer_budget,
        seller_reservation_price=seller_reservation_price,
        max_turns=config.max_turns,
        metadata={
            "scenario_config_id": config.id,
            **dict(config.metadata or {}),
        },
    )


def _select_product(path: Path, product_id: str | None, product_index: int) -> Product:
    products = _load_products(path)
    if product_id is not None:
        for product in products:
            if product.id == product_id:
                return product
        raise ConfigValidationError(f"{path}: product_id {product_id!r} not found")
    if product_index < 0 or product_index >= len(products):
        raise ConfigValidationError(
            f"{path}: product_index {product_index} out of range for {len(products)} products"
        )
    return products[product_index]


def _load_products(path: Path) -> list[Product]:
    if not path.exists():
        raise ConfigValidationError(f"{path}: products_file does not exist")
    try:
        records = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(f"{path}: expected JSON product list") from exc
    if not isinstance(records, list) or not records:
        raise ConfigValidationError(f"{path}: expected non-empty product list")
    try:
        return [Product.from_mapping(record) for record in records]
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(f"{path}: invalid product record: {exc}") from exc


def _build_tools(
    tool_regime: ToolRegimeConfig,
) -> tuple[tuple[ToolPort, ...], tuple[ToolRuntimeConfig, ...]]:
    tools: list[ToolPort] = []
    configs: list[ToolRuntimeConfig] = []
    for spec in tool_regime.tools:
        if not spec.enabled:
            continue
        if spec.kind != "market_price":
            raise ConfigValidationError(
                f"tool_regimes[{tool_regime.id}].tools[{spec.name}].kind: "
                f"unsupported kind {spec.kind!r}"
            )
        if spec.name != "market_price_search":
            raise ConfigValidationError(
                f"tool_regimes[{tool_regime.id}].tools[{spec.name}].name: "
                "only 'market_price_search' is supported in this runner slice"
            )
        if spec.source is None:
            raise ConfigValidationError(f"tool {spec.name}: source is required")
        if not spec.source.exists():
            raise ConfigValidationError(f"{spec.source}: tool source does not exist")
        tools.append(
            MarketPriceTool.from_json(
                spec.source,
                mode=spec.mode,
                noise_fraction=_metadata_float(spec.metadata, "noise_fraction", 0.1),
                adversarial_multiplier=_metadata_float(
                    spec.metadata,
                    "adversarial_multiplier",
                    1.25,
                ),
                stale_as_of=_metadata_str(spec.metadata, "stale_as_of"),
            )
        )
        configs.append(
            ToolRuntimeConfig(
                name=spec.name,
                roles=_roles_for_tool(spec),
                visibility=_visibility_for_tool(spec.visibility),
                fail_fast=spec.fail_fast,
            )
        )
    return tuple(tools), tuple(configs)


def _tool_regime_metadata(tool_regime: ToolRegimeConfig) -> Mapping[str, Any]:
    return {
        "id": tool_regime.id,
        "tools": [
            {
                "name": spec.name,
                "kind": spec.kind,
                "source": str(spec.source) if spec.source else None,
                "visibility": spec.visibility,
                "roles": [role.value for role in _roles_for_tool(spec)],
                "mode": spec.mode,
                "fail_fast": spec.fail_fast,
                "enabled": spec.enabled,
                "metadata": dict(spec.metadata or {}),
            }
            for spec in tool_regime.tools
        ],
        "metadata": dict(tool_regime.metadata or {}),
    }


def _is_completed_run(output_dir: Path, run_id: str) -> bool:
    try:
        manifest = load_manifest(output_dir / "manifest.json")
        load_scenario_artifact(output_dir / "scenario.json")
        load_trace(output_dir / "trace.jsonl")
        load_metric_report(output_dir / "metrics.json")
    except (OSError, ArtifactValidationError, json.JSONDecodeError):
        return False
    return manifest.run_id == run_id


def _run_id(
    experiment_name: str,
    scenario_id: str,
    tool_regime_id: str,
    seed: int | None,
) -> str:
    seed_part = "seed-none" if seed is None else f"seed-{seed}"
    return _slug(f"{experiment_name}-{scenario_id}-{tool_regime_id}-{seed_part}")


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    if not slug:
        raise ConfigValidationError("run_id: generated empty id")
    return slug


def _validate_run_ids(prepared_runs: Sequence[PreparedRun]) -> None:
    seen: set[str] = set()
    for prepared_run in prepared_runs:
        if prepared_run.run_id in seen:
            raise ConfigValidationError(f"run_id collision: {prepared_run.run_id}")
        seen.add(prepared_run.run_id)


def _read_config_mapping(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise ConfigValidationError(f"{path}: config file does not exist")
    text = path.read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as json_exc:
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise ConfigValidationError(f"{path}: expected JSON object") from json_exc
        try:
            import yaml  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:
            raise ConfigValidationError(
                f"{path}: YAML syntax requires PyYAML; use JSON-compatible YAML "
                "or install the optional parser"
            ) from exc
        data = yaml.safe_load(text)
    if not isinstance(data, Mapping):
        raise ConfigValidationError(f"{path}: expected config object")
    return data


def _parse_scenario(data: Any, index: int) -> ScenarioConfig:
    if not isinstance(data, Mapping):
        raise ConfigValidationError(f"scenarios[{index}]: expected object")
    products_file = Path(_required_str(data, "products_file"))
    product_id = _optional_str(data, "product_id")
    product_index = _optional_int(data, "product_index", 0)
    buyer_budget = _optional_float(data, "buyer_budget")
    seller_reservation_price = _optional_float(data, "seller_reservation_price")
    max_turns = _optional_int(data, "max_turns", 8)
    if max_turns <= 0:
        raise ConfigValidationError(
            f"scenarios[{index}].max_turns: expected positive integer"
        )
    return ScenarioConfig(
        id=_optional_str(data, "id"),
        products_file=products_file,
        product_id=product_id,
        product_index=product_index,
        buyer_budget=buyer_budget,
        seller_reservation_price=seller_reservation_price,
        max_turns=max_turns,
        metadata=_optional_mapping(data, "metadata"),
    )


def _parse_tool_regime(data: Any, index: int) -> ToolRegimeConfig:
    if not isinstance(data, Mapping):
        raise ConfigValidationError(f"tool_regimes[{index}]: expected object")
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        raise ConfigValidationError(f"tool_regimes[{index}].tools: expected list")
    return ToolRegimeConfig(
        id=_required_str(data, "id"),
        tools=tuple(
            _parse_tool_spec(item, index, tool_index)
            for tool_index, item in enumerate(tools)
        ),
        metadata=_optional_mapping(data, "metadata"),
    )


def _parse_tool_spec(data: Any, regime_index: int, tool_index: int) -> ToolSpec:
    if not isinstance(data, Mapping):
        raise ConfigValidationError(
            f"tool_regimes[{regime_index}].tools[{tool_index}]: expected object"
        )
    source = _optional_str(data, "source")
    visibility = _optional_str(data, "visibility") or "private"
    mode = _optional_str(data, "mode") or "clean"
    if mode not in {"clean", "noisy", "stale", "adversarial", "failure"}:
        raise ConfigValidationError(
            f"tool_regimes[{regime_index}].tools[{tool_index}].mode: "
            f"unsupported mode {mode!r}"
        )
    roles = _optional_roles(data, "roles")
    return ToolSpec(
        name=_required_str(data, "name"),
        kind=_required_str(data, "kind"),
        source=Path(source) if source else None,
        visibility=visibility,
        roles=roles,
        mode=mode,
        fail_fast=_optional_bool(data, "fail_fast", False),
        enabled=_optional_bool(data, "enabled", True),
        metadata=_optional_mapping(data, "metadata"),
    )


def _parse_agents(data: Mapping[str, Any]) -> AgentPairConfig:
    buyer = _required_mapping(data, "buyer")
    seller = _required_mapping(data, "seller")
    return AgentPairConfig(
        buyer=_parse_agent_spec(buyer, "agents.buyer"),
        seller=_parse_agent_spec(seller, "agents.seller"),
    )


def _parse_agent_spec(data: Mapping[str, Any], path: str) -> AgentSpecConfig:
    params = data.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        raise ConfigValidationError(f"{path}.params: expected object")
    return AgentSpecConfig(
        kind=_required_str(data, "kind"),
        params=dict(params),
    )


def _parse_transaction_config(data: Any) -> TransactionConfig | None:
    if data is None:
        return None
    if not isinstance(data, Mapping):
        raise ConfigValidationError("transaction: expected object")
    kind = _optional_str(data, "kind") or "fixture"
    if kind != "fixture":
        raise ConfigValidationError(f"transaction.kind: unsupported kind {kind!r}")
    return TransactionConfig(
        kind=kind,
        enabled=_optional_bool(data, "enabled", True),
        shipping_cost=_optional_float(data, "shipping_cost") or 0.0,
        tax_rate=_optional_float(data, "tax_rate") or 0.0,
        escrow_fee=_optional_float(data, "escrow_fee") or 0.0,
        payment_fee_rate=_optional_float(data, "payment_fee_rate") or 0.0,
        seller_fee_rate=_optional_float(data, "seller_fee_rate") or 0.0,
        return_risk=_optional_float(data, "return_risk") or 0.0,
        reputation_risk=_optional_float(data, "reputation_risk") or 0.0,
        dispute_risk=_optional_float(data, "dispute_risk") or 0.0,
        payment_success=_optional_bool(data, "payment_success", True),
        shipping_success=_optional_bool(data, "shipping_success", True),
        item_matches_listing=_optional_bool(data, "item_matches_listing", True),
        max_buyer_total_cost=_optional_float(data, "max_buyer_total_cost"),
        min_seller_net_revenue=_optional_float(data, "min_seller_net_revenue"),
        max_dispute_risk=_optional_float(data, "max_dispute_risk"),
        return_window_days=_optional_nullable_int(data, "return_window_days"),
        min_return_window_days=_optional_nullable_int(data, "min_return_window_days"),
        payment_method=_optional_str(data, "payment_method"),
        payment_processor=_optional_str(data, "payment_processor"),
        escrow_release_policy=_optional_str(data, "escrow_release_policy"),
        shipping_carrier=_optional_str(data, "shipping_carrier"),
        shipping_service=_optional_str(data, "shipping_service"),
        tracking_required=_optional_bool(data, "tracking_required", False),
        delivery_days=_optional_nullable_int(data, "delivery_days"),
        max_delivery_days=_optional_nullable_int(data, "max_delivery_days"),
        return_shipping_payer=_optional_str(data, "return_shipping_payer"),
        inspection_period_days=_optional_nullable_int(data, "inspection_period_days"),
        warranty_days=_optional_nullable_int(data, "warranty_days"),
        min_warranty_days=_optional_nullable_int(data, "min_warranty_days"),
        warranty_provider=_optional_str(data, "warranty_provider"),
        compliance_checks=_optional_string_tuple(data, "compliance_checks"),
        compliance_passed=_optional_bool(data, "compliance_passed", True),
        dispute_window_days=_optional_nullable_int(data, "dispute_window_days"),
        dispute_resolution_policy=_optional_str(data, "dispute_resolution_policy"),
        failure_reason=_optional_str(data, "failure_reason"),
        metadata=_optional_mapping(data, "metadata"),
    )


def _build_transaction_simulator(
    config: TransactionConfig | None,
) -> FixtureTransactionSimulator | None:
    if config is None or not config.enabled:
        return None
    return FixtureTransactionSimulator(
        shipping_cost=config.shipping_cost,
        tax_rate=config.tax_rate,
        escrow_fee=config.escrow_fee,
        payment_fee_rate=config.payment_fee_rate,
        seller_fee_rate=config.seller_fee_rate,
        return_risk=config.return_risk,
        reputation_risk=config.reputation_risk,
        dispute_risk=config.dispute_risk,
        payment_success=config.payment_success,
        shipping_success=config.shipping_success,
        item_matches_listing=config.item_matches_listing,
        max_buyer_total_cost=config.max_buyer_total_cost,
        min_seller_net_revenue=config.min_seller_net_revenue,
        max_dispute_risk=config.max_dispute_risk,
        return_window_days=config.return_window_days,
        min_return_window_days=config.min_return_window_days,
        payment_method=config.payment_method,
        payment_processor=config.payment_processor,
        escrow_release_policy=config.escrow_release_policy,
        shipping_carrier=config.shipping_carrier,
        shipping_service=config.shipping_service,
        tracking_required=config.tracking_required,
        delivery_days=config.delivery_days,
        max_delivery_days=config.max_delivery_days,
        return_shipping_payer=config.return_shipping_payer,
        inspection_period_days=config.inspection_period_days,
        warranty_days=config.warranty_days,
        min_warranty_days=config.min_warranty_days,
        warranty_provider=config.warranty_provider,
        compliance_checks=config.compliance_checks,
        compliance_passed=config.compliance_passed,
        dispute_window_days=config.dispute_window_days,
        dispute_resolution_policy=config.dispute_resolution_policy,
        failure_reason=config.failure_reason,
        metadata=dict(config.metadata or {}),
    )


def _transaction_metadata(config: TransactionConfig | None) -> Mapping[str, Any]:
    if config is None:
        return {"enabled": False}
    return {
        "kind": config.kind,
        "enabled": config.enabled,
        "shipping_cost": config.shipping_cost,
        "tax_rate": config.tax_rate,
        "escrow_fee": config.escrow_fee,
        "payment_fee_rate": config.payment_fee_rate,
        "seller_fee_rate": config.seller_fee_rate,
        "return_risk": config.return_risk,
        "reputation_risk": config.reputation_risk,
        "dispute_risk": config.dispute_risk,
        "payment_success": config.payment_success,
        "shipping_success": config.shipping_success,
        "item_matches_listing": config.item_matches_listing,
        "max_buyer_total_cost": config.max_buyer_total_cost,
        "min_seller_net_revenue": config.min_seller_net_revenue,
        "max_dispute_risk": config.max_dispute_risk,
        "return_window_days": config.return_window_days,
        "min_return_window_days": config.min_return_window_days,
        "payment_method": config.payment_method,
        "payment_processor": config.payment_processor,
        "escrow_release_policy": config.escrow_release_policy,
        "shipping_carrier": config.shipping_carrier,
        "shipping_service": config.shipping_service,
        "tracking_required": config.tracking_required,
        "delivery_days": config.delivery_days,
        "max_delivery_days": config.max_delivery_days,
        "return_shipping_payer": config.return_shipping_payer,
        "inspection_period_days": config.inspection_period_days,
        "warranty_days": config.warranty_days,
        "min_warranty_days": config.min_warranty_days,
        "warranty_provider": config.warranty_provider,
        "compliance_checks": list(config.compliance_checks),
        "compliance_passed": config.compliance_passed,
        "dispute_window_days": config.dispute_window_days,
        "dispute_resolution_policy": config.dispute_resolution_policy,
        "failure_reason": config.failure_reason,
        "metadata": dict(config.metadata or {}),
    }


def _parse_seeds(value: Any) -> tuple[int | None, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigValidationError("seeds: expected non-empty list")
    seeds: list[int | None] = []
    for index, seed in enumerate(value):
        if seed is None:
            seeds.append(None)
        elif isinstance(seed, int):
            seeds.append(seed)
        else:
            raise ConfigValidationError(f"seeds[{index}]: expected integer or null")
    return tuple(seeds)


def _required_list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ConfigValidationError(f"{key}: expected list")
    return value


def _required_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ConfigValidationError(f"{key}: expected object")
    return value


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigValidationError(f"{key}: expected non-empty string")
    return value


def _optional_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigValidationError(f"{key}: expected object")
    return value


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigValidationError(f"{key}: expected string")
    return value


def _optional_bool(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigValidationError(f"{key}: expected boolean")
    return value


def _optional_int(data: Mapping[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ConfigValidationError(f"{key}: expected integer")
    return value


def _optional_nullable_int(data: Mapping[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ConfigValidationError(f"{key}: expected integer or null")
    return value


def _optional_float(data: Mapping[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ConfigValidationError(f"{key}: expected number")
    return float(value)


def _optional_roles(data: Mapping[str, Any], key: str) -> tuple[Role, ...] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ConfigValidationError(f"{key}: expected non-empty list")
    roles: list[Role] = []
    for index, role in enumerate(value):
        if not isinstance(role, str):
            raise ConfigValidationError(f"{key}[{index}]: expected string")
        try:
            roles.append(Role(role))
        except ValueError as exc:
            raise ConfigValidationError(f"{key}[{index}]: unsupported role {role!r}") from exc
    return tuple(roles)


def _optional_string_tuple(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigValidationError(f"{key}: expected list")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ConfigValidationError(
                f"{key}[{index}]: expected non-empty string"
            )
        items.append(item.strip())
    return tuple(items)


def _roles_for_tool(spec: ToolSpec) -> tuple[Role, ...]:
    if spec.roles is not None:
        return spec.roles
    visibility = spec.visibility
    if visibility == "buyer_private":
        return (Role.BUYER,)
    if visibility == "seller_private":
        return (Role.SELLER,)
    if visibility in {
        "private",
        "public",
        "symmetric_private",
        "symmetric_public",
        "shared_private",
        "shared_public",
    }:
        return (Role.BUYER, Role.SELLER)
    raise ConfigValidationError(f"visibility: unsupported value {visibility!r}")


def _visibility_for_tool(value: str) -> str:
    if value in {"public", "symmetric_public", "shared_public"}:
        return "public"
    if value in {
        "private",
        "buyer_private",
        "seller_private",
        "symmetric_private",
        "shared_private",
    }:
        return "private"
    raise ConfigValidationError(f"visibility: unsupported value {value!r}")


def _metadata_float(
    metadata: Mapping[str, Any] | None,
    key: str,
    default: float,
) -> float:
    value = (metadata or {}).get(key, default)
    if not isinstance(value, (int, float)):
        raise ConfigValidationError(f"metadata.{key}: expected number")
    return float(value)


def _metadata_str(metadata: Mapping[str, Any] | None, key: str) -> str | None:
    value = (metadata or {}).get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigValidationError(f"metadata.{key}: expected string")
    return value
