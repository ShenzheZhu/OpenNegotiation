"""Small live-model demo runner for OpenNego."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from opennego.adapters import LiteLLMGateway
from opennego.agents import ScriptedSeller, make_llm_buyer
from opennego.artifacts import ArtifactPaths, write_run_artifacts
from opennego.environment import NegotiationEnvironment, ToolRuntimeConfig
from opennego.ports import LLMPort, LLMRequest, LLMResponse
from opennego.schema import Product, Role, Scenario
from opennego.tools import MarketPriceTool
from opennego.transactions import FixtureTransactionSimulator

DEFAULT_MODEL_DEMO_MODELS: tuple[str, ...] = (
    "openrouter/openai/gpt-4o-mini",
    "openrouter/anthropic/claude-3.5-haiku",
    "openrouter/google/gemini-2.5-flash-lite",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
    "openrouter/mistralai/mistral-small-3.2-24b-instruct",
)


@dataclass(frozen=True)
class ModelDemoRecord:
    model: str
    status: str
    output_dir: str
    outcome: str | None = None
    deal_price: float | None = None
    completed_turns: int | None = None
    llm_call_count: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class ModelDemoSummary:
    name: str
    output_dir: str
    total_runs: int
    completed: int
    failed: int
    runs: tuple[ModelDemoRecord, ...]


class RecordingLLMPort:
    """Records provider usage while preserving the LLMPort interface."""

    def __init__(self, inner: LLMPort) -> None:
        self.inner = inner
        self.requests: list[LLMRequest] = []
        self.responses: list[LLMResponse] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        response = self.inner.complete(request)
        self.responses.append(response)
        return response

    @property
    def usage_summary(self) -> Mapping[str, float | int | None]:
        prompt_tokens = _sum_optional(response.usage.prompt_tokens for response in self.responses)
        completion_tokens = _sum_optional(response.usage.completion_tokens for response in self.responses)
        total_tokens = _sum_optional(response.usage.total_tokens for response in self.responses)
        cost_usd = _sum_optional_float(response.usage.cost_usd for response in self.responses)
        return {
            "llm_call_count": len(self.requests),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
        }


def run_model_demo(
    *,
    models: Sequence[str] = DEFAULT_MODEL_DEMO_MODELS,
    output_dir: str | Path = "runs/five_model_demo",
    products_file: str | Path = "examples/data/real_market_products.json",
    market_comps_file: str | Path = "examples/data/real_market_comps.json",
    max_turns: int = 6,
    temperature: float = 0.0,
    max_tokens: int | None = 384,
    fail_fast: bool = False,
    llm_factory=None,
) -> ModelDemoSummary:
    product = _load_first_product(products_file)
    scenario = Scenario(
        product=product,
        buyer_budget=float(product.attributes.get("buyer_budget", product.list_price * 0.85)),
        seller_reservation_price=product.wholesale_price,
        max_turns=max_turns,
        metadata={"scenario_config_id": "five_model_demo"},
    )
    market_tool = MarketPriceTool.from_json(market_comps_file)
    transaction = FixtureTransactionSimulator(
        shipping_cost=12.0,
        tax_rate=0.06,
        escrow_fee=3.0,
        payment_fee_rate=0.015,
        seller_fee_rate=0.04,
        return_risk=0.02,
        reputation_risk=0.01,
    )
    base_output_dir = Path(output_dir)
    records: list[ModelDemoRecord] = []
    for model in models:
        run_id = f"five_model_demo-{_slug_model(model)}"
        run_output_dir = base_output_dir / run_id
        recorder = RecordingLLMPort((llm_factory or LiteLLMGateway)())
        buyer = make_llm_buyer(
            llm=recorder,
            model=model,
            name=f"llm_buyer:{_short_model_name(model)}",
            tool_policy="available",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            env = NegotiationEnvironment(
                scenario=scenario,
                buyer=buyer,
                seller=ScriptedSeller(),
                tools=(market_tool,),
                tool_configs=(
                    ToolRuntimeConfig(
                        name="market_price_search",
                        roles=(Role.BUYER,),
                        visibility="private",
                    ),
                ),
                transaction_simulator=transaction,
            )
            result = env.run()
            paths = _write_model_run(
                result=result,
                output_dir=run_output_dir,
                run_id=run_id,
                model=model,
                usage=recorder.usage_summary,
            )
            records.append(
                ModelDemoRecord(
                    model=model,
                    status="completed",
                    output_dir=str(paths.output_dir),
                    outcome=result.outcome,
                    deal_price=result.deal_price,
                    completed_turns=result.completed_turns,
                    llm_call_count=int(recorder.usage_summary["llm_call_count"] or 0),
                    prompt_tokens=_optional_int(recorder.usage_summary["prompt_tokens"]),
                    completion_tokens=_optional_int(recorder.usage_summary["completion_tokens"]),
                    total_tokens=_optional_int(recorder.usage_summary["total_tokens"]),
                    cost_usd=_optional_float(recorder.usage_summary["cost_usd"]),
                )
            )
        except Exception as exc:
            records.append(
                ModelDemoRecord(
                    model=model,
                    status="failed",
                    output_dir=str(run_output_dir),
                    llm_call_count=int(recorder.usage_summary["llm_call_count"] or 0),
                    error=str(exc),
                )
            )
            if fail_fast:
                break

    return ModelDemoSummary(
        name="five_model_demo",
        output_dir=str(base_output_dir),
        total_runs=len(models),
        completed=sum(1 for record in records if record.status == "completed"),
        failed=sum(1 for record in records if record.status == "failed"),
        runs=tuple(records),
    )


def _write_model_run(
    *,
    result,
    output_dir: Path,
    run_id: str,
    model: str,
    usage: Mapping[str, float | int | None],
) -> ArtifactPaths:
    return write_run_artifacts(
        result=result,
        output_dir=output_dir,
        run_id=run_id,
        scenario_id="iphone_14_pro_128gb_unlocked_good",
        agents={
            "buyer": {"name": f"llm_buyer:{_short_model_name(model)}", "kind": "llm_buyer"},
            "seller": {"name": "scripted_seller", "kind": "scripted_seller"},
        },
        models={
            "buyer": model,
            "seller": "scripted_seller",
        },
        tool_regime={
            "id": "buyer_private_market_search",
            "tools": [
                {
                    "name": "market_price_search",
                    "kind": "market_price",
                    "source": "examples/data/real_market_comps.json",
                    "visibility": "buyer_private",
                    "mode": "clean",
                }
            ],
        },
        metadata={
            "experiment_name": "five_model_demo",
            "llm_usage": dict(usage),
        },
    )


def _load_first_product(path: str | Path) -> Product:
    records = json.loads(Path(path).read_text())
    if not records:
        raise ValueError(f"No products found in {path}")
    return Product.from_mapping(records[0])


def _slug_model(model: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in model).strip("-").lower()


def _short_model_name(model: str) -> str:
    return model.removeprefix("openrouter/")


def _sum_optional(values) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _sum_optional_float(values) -> float | None:
    present = [value for value in values if value is not None]
    return round(sum(float(value) for value in present), 8) if present else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
