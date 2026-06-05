"""Shared schema for negotiation environments, agents, and tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class Role(str, Enum):
    BUYER = "buyer"
    SELLER = "seller"


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    OFFER = "offer"
    ACCEPT = "accept"
    REJECT = "reject"
    MESSAGE = "message"


def parse_price(value: Any) -> float:
    """Parse a numeric price from common JSON encodings."""

    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        return float(cleaned)
    raise TypeError(f"Unsupported price value: {value!r}")


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    description: str
    list_price: float
    wholesale_price: float
    condition: str = "unknown"
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Product":
        """Load either OpenNego or A2A-NT-style product records."""

        name = data.get("name") or data.get("Product Name")
        if not name:
            raise ValueError("Product record must include name or Product Name")

        list_price = data.get("list_price", data.get("Retail Price"))
        wholesale_price = data.get("wholesale_price", data.get("Wholesale Price"))
        if list_price is None or wholesale_price is None:
            raise ValueError("Product record must include list and wholesale prices")

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
            "wholesale_price",
            "Wholesale Price",
            "condition",
        }
        attributes = {key: value for key, value in data.items() if key not in known_keys}
        return cls(
            id=product_id,
            name=str(name),
            description=str(description),
            list_price=parse_price(list_price),
            wholesale_price=parse_price(wholesale_price),
            condition=condition,
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
