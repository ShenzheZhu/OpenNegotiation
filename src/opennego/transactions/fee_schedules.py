"""Published marketplace fee schedules with provenance.

Each schedule entry mirrors a real platform's published pricing and must
carry ``source_url`` and ``as_of`` so settlement economics stay auditable.
Schedules feed the fixture transaction simulator through the experiment
config ``transaction.schedule`` key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

FEE_SCHEDULE_SCHEMA_VERSION = "opennego.fee_schedule.v1"
DEFAULT_FEE_SCHEDULES_PATH = Path(__file__).parent / "data" / "fee_schedules.json"


class FeeScheduleError(ValueError):
    """Raised when a fee schedule is missing, malformed, or unprovenanced."""


@dataclass(frozen=True)
class FeeSchedule:
    id: str
    platform: str
    as_of: str
    source_url: str
    currency: str = "USD"
    seller_fee_tiers: tuple[tuple[float | None, float], ...] = ()
    seller_fee_rate: float = 0.0
    seller_fee_fixed: float = 0.0
    payment_fee_rate: float = 0.0
    payment_fee_fixed: float = 0.0
    tax_rate: float = 0.0
    shipping_cost: float = 0.0
    escrow_fee: float = 0.0
    description: str = ""
    notes: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


def available_fee_schedules(
    schedules_file: str | Path | None = None,
) -> tuple[str, ...]:
    data = _read_schedules(schedules_file)
    return tuple(sorted(data))


def load_fee_schedule(
    schedule_id: str,
    *,
    schedules_file: str | Path | None = None,
) -> FeeSchedule:
    schedules = _read_schedules(schedules_file)
    raw = schedules.get(schedule_id)
    if raw is None:
        raise FeeScheduleError(
            f"unknown fee schedule {schedule_id!r}; "
            f"available: {', '.join(sorted(schedules))}"
        )
    return _parse_schedule(schedule_id, raw)


def _read_schedules(
    schedules_file: str | Path | None,
) -> Mapping[str, Mapping[str, Any]]:
    path = Path(schedules_file) if schedules_file is not None else (
        DEFAULT_FEE_SCHEDULES_PATH
    )
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise FeeScheduleError(f"cannot read fee schedules from {path}: {exc}") from exc
    except ValueError as exc:
        raise FeeScheduleError(f"invalid fee schedule JSON in {path}: {exc}") from exc
    if data.get("schema_version") != FEE_SCHEDULE_SCHEMA_VERSION:
        raise FeeScheduleError(
            "fee schedules schema_version: expected "
            f"{FEE_SCHEDULE_SCHEMA_VERSION!r}, got {data.get('schema_version')!r}"
        )
    schedules = data.get("schedules")
    if not isinstance(schedules, Mapping) or not schedules:
        raise FeeScheduleError("fee schedules: expected non-empty 'schedules' object")
    return schedules


def _parse_schedule(schedule_id: str, raw: Mapping[str, Any]) -> FeeSchedule:
    errors = []
    for required in ("platform", "as_of", "source_url"):
        if not raw.get(required):
            errors.append(f"{required}: required for provenance")
    tiers = []
    raw_tiers = raw.get("seller_fee_tiers", [])
    if not isinstance(raw_tiers, list):
        errors.append("seller_fee_tiers: expected list")
        raw_tiers = []
    previous_cap = 0.0
    for index, tier in enumerate(raw_tiers):
        if not isinstance(tier, Mapping) or "rate" not in tier:
            errors.append(f"seller_fee_tiers[{index}]: expected object with rate")
            continue
        cap = tier.get("up_to")
        if cap is not None:
            cap = float(cap)
            if cap <= previous_cap:
                errors.append(
                    f"seller_fee_tiers[{index}].up_to: expected increasing caps"
                )
            previous_cap = cap
        elif index != len(raw_tiers) - 1:
            errors.append(
                f"seller_fee_tiers[{index}].up_to: only the last tier may be open"
            )
        tiers.append((cap, float(tier["rate"])))
    if errors:
        raise FeeScheduleError(
            f"fee schedule {schedule_id!r}: " + "; ".join(errors)
        )
    return FeeSchedule(
        id=schedule_id,
        platform=str(raw["platform"]),
        as_of=str(raw["as_of"]),
        source_url=str(raw["source_url"]),
        currency=str(raw.get("currency", "USD")),
        seller_fee_tiers=tuple(tiers),
        seller_fee_rate=float(raw.get("seller_fee_rate", 0.0)),
        seller_fee_fixed=float(raw.get("seller_fee_fixed", 0.0)),
        payment_fee_rate=float(raw.get("payment_fee_rate", 0.0)),
        payment_fee_fixed=float(raw.get("payment_fee_fixed", 0.0)),
        tax_rate=float(raw.get("tax_rate", 0.0)),
        shipping_cost=float(raw.get("shipping_cost", 0.0)),
        escrow_fee=float(raw.get("escrow_fee", 0.0)),
        description=str(raw.get("description", "")),
        notes=str(raw.get("notes", "")),
        metadata=dict(raw.get("metadata", {})),
    )


def tiered_seller_fee(
    price: float,
    tiers: tuple[tuple[float | None, float], ...],
    *,
    fallback_rate: float = 0.0,
    fixed: float = 0.0,
) -> float:
    """Compute a marginal tiered fee like real final-value-fee schedules."""

    if not tiers:
        return round(price * fallback_rate + fixed, 2)
    fee = 0.0
    lower = 0.0
    remaining = price
    for cap, rate in tiers:
        if remaining <= 0:
            break
        band = remaining if cap is None else min(remaining, cap - lower)
        fee += band * rate
        remaining -= band
        if cap is not None:
            lower = cap
    return round(fee + fixed, 2)
