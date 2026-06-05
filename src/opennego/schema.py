"""Shared schema for negotiation environments, agents, and tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class Role(str, Enum):
    BUYER = "buyer"
    SELLER = "seller"
    SYSTEM = "system"


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    OFFER = "offer"
    ACCEPT = "accept"
    REJECT = "reject"
    MESSAGE = "message"
    TRANSACTION = "transaction"


def parse_price(value: Any) -> float:
    """Parse a numeric price from common JSON encodings."""

    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        return float(cleaned)
    raise TypeError(f"Unsupported price value: {value!r}")


@dataclass(frozen=True)
class MarketReference:
    reference_price: float
    p25_price: float | None = None
    p75_price: float | None = None
    sample_size: int | None = None
    currency: str = "USD"
    window_days: int | None = None
    source: str = "unknown"
    sale_mechanism: str = "mixed"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MarketReference":
        reference_price = (
            data.get("reference_price")
            if data.get("reference_price") is not None
            else data.get("median_price", data.get("market_median_price"))
        )
        if reference_price is None:
            raise ValueError("market_reference must include reference_price or median_price")

        known_keys = {
            "reference_price",
            "median_price",
            "market_median_price",
            "p25_price",
            "p25",
            "q1_price",
            "p75_price",
            "p75",
            "q3_price",
            "sample_size",
            "currency",
            "window_days",
            "source",
            "sale_mechanism",
        }
        sample_size = data.get("sample_size")
        window_days = data.get("window_days")
        return cls(
            reference_price=parse_price(reference_price),
            p25_price=_optional_price(data.get("p25_price", data.get("p25", data.get("q1_price")))),
            p75_price=_optional_price(data.get("p75_price", data.get("p75", data.get("q3_price")))),
            sample_size=int(sample_size) if sample_size is not None else None,
            currency=str(data.get("currency", "USD")),
            window_days=int(window_days) if window_days is not None else None,
            source=str(data.get("source", "unknown")),
            sale_mechanism=str(data.get("sale_mechanism", "mixed")),
            metadata={key: value for key, value in data.items() if key not in known_keys},
        )

    @property
    def iqr(self) -> float | None:
        if self.p25_price is None or self.p75_price is None:
            return None
        spread = self.p75_price - self.p25_price
        if spread <= 0:
            return None
        return spread


def _optional_price(value: Any) -> float | None:
    if value is None:
        return None
    return parse_price(value)


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    description: str
    list_price: float
    wholesale_price: float
    condition: str = "unknown"
    market_reference: MarketReference | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Product":
        """Load either OpenNego or A2A-NT-style product records."""

        name = data.get("name") or data.get("Product Name")
        if not name:
            raise ValueError("Product record must include name or Product Name")

        raw_market_reference = data.get("market_reference")
        market_reference = None
        if raw_market_reference is not None:
            if not isinstance(raw_market_reference, Mapping):
                raise ValueError("market_reference must be an object")
            market_reference = MarketReference.from_mapping(raw_market_reference)

        list_price = data.get(
            "list_price",
            data.get("Retail Price", data.get("asking_price", data.get("initial_listing_price"))),
        )
        if list_price is None:
            raise ValueError("Product record must include list, retail, or asking price")

        wholesale_price = data.get("wholesale_price", data.get("Wholesale Price"))
        legacy_wholesale_basis = None
        if wholesale_price is None:
            wholesale_price = data.get(
                "synthetic_seller_reservation_price",
                data.get("seller_reservation_price", data.get("reservation_price")),
            )
            if wholesale_price is not None:
                legacy_wholesale_basis = "synthetic_seller_reservation_price"
        if wholesale_price is None and market_reference is not None:
            wholesale_price = market_reference.p25_price or market_reference.reference_price
            legacy_wholesale_basis = (
                "market_reference.p25_price"
                if market_reference.p25_price is not None
                else "market_reference.reference_price"
            )
        if wholesale_price is None:
            raise ValueError(
                "Product record must include wholesale price, synthetic reservation, "
                "or market_reference"
            )

        description = data.get("description") or data.get("Features") or ""
        product_id = str(data.get("id", name))
        condition = str(data.get("condition", "unknown"))
        known_keys = {
            "id",
            "name",
            "Product Name",
            "description",
            "Features",
            "list_price",
            "Retail Price",
            "asking_price",
            "initial_listing_price",
            "wholesale_price",
            "Wholesale Price",
            "condition",
            "market_reference",
        }
        attributes = {key: value for key, value in data.items() if key not in known_keys}
        if legacy_wholesale_basis is not None:
            attributes = {
                **attributes,
                "legacy_wholesale_basis": legacy_wholesale_basis,
            }
        return cls(
            id=product_id,
            name=str(name),
            description=str(description),
            list_price=parse_price(list_price),
            wholesale_price=parse_price(wholesale_price),
            condition=condition,
            market_reference=market_reference,
            attributes=attributes,
        )


@dataclass(frozen=True)
class Scenario:
    product: Product
    buyer_budget: float
    seller_reservation_price: float
    max_turns: int = 12
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.buyer_budget <= 0:
            raise ValueError("buyer_budget must be positive")
        if self.seller_reservation_price <= 0:
            raise ValueError("seller_reservation_price must be positive")
        if self.max_turns <= 0:
            raise ValueError("max_turns must be positive")


@dataclass(frozen=True)
class Offer:
    price: float
    note: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("offer price must be positive")


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentAction:
    type: ActionType
    content: str = ""
    offer: Offer | None = None
    tool_call: ToolCall | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", ActionType(self.type))

    @classmethod
    def tool(cls, name: str, arguments: Mapping[str, Any] | None = None) -> "AgentAction":
        return cls(type=ActionType.TOOL_CALL, tool_call=ToolCall(name, arguments or {}))

    @classmethod
    def offer_price(cls, price: float, note: str = "") -> "AgentAction":
        return cls(type=ActionType.OFFER, offer=Offer(price=price, note=note), content=note)

    @classmethod
    def accept(cls, note: str = "") -> "AgentAction":
        return cls(type=ActionType.ACCEPT, content=note)

    @classmethod
    def reject(cls, note: str = "") -> "AgentAction":
        return cls(type=ActionType.REJECT, content=note)

    @classmethod
    def message(cls, content: str) -> "AgentAction":
        return cls(type=ActionType.MESSAGE, content=content)


@dataclass(frozen=True)
class TranscriptEvent:
    turn: int
    role: Role
    actor: str
    action_type: ActionType
    content: str = ""
    offer: Offer | None = None
    tool_call: ToolCall | None = None
    tool_result: Mapping[str, Any] | None = None
    transaction: "TransactionOutcome | None" = None
    private: bool = False


@dataclass(frozen=True)
class AgentContext:
    scenario: Scenario
    role: Role
    transcript: Sequence[TranscriptEvent]
    available_tools: Sequence[str] = field(default_factory=tuple)
    private_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    scenario: Scenario
    events: Sequence[TranscriptEvent]
    outcome: str
    deal_price: float | None
    completed_turns: int
    metrics: Mapping[str, float]
    transaction: "TransactionOutcome | None" = None


@dataclass(frozen=True)
class TransactionOutcome:
    status: str
    negotiated_price: float
    buyer_total_cost: float
    seller_net_revenue: float
    shipping_cost: float = 0.0
    tax: float = 0.0
    escrow_fee: float = 0.0
    payment_fee: float = 0.0
    seller_fee: float = 0.0
    return_risk: float = 0.0
    reputation_risk: float = 0.0
    dispute_risk: float = 0.0
    risk_exposure: float = 0.0
    failure_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"completed", "failed"}:
            raise ValueError("transaction status must be 'completed' or 'failed'")
