"""Realism calibration: sandbox distributions vs real-market reference.

See ``docs/design/market.md``. This is the operational form of the roadmap's
transfer north star: a market episode is only worth as much as it resembles
reality. ``calibrate_episode`` compares the sandbox's clearing-price, round-
count, and deal-rate statistics against a reference (real eBay sold data, or a
fixture reference for no-key CI) and reports a per-metric within-tolerance
verdict and an overall status. It reports the gap; it does not close it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from opennego.artifacts import to_jsonable, write_json
from opennego.market_runtime import MarketEpisodeResult

MARKET_CALIBRATION_SCHEMA_VERSION = "opennego.market_calibration.v1"


class CalibrationError(ValueError):
    """Raised when calibration inputs are malformed."""


@dataclass(frozen=True)
class MetricVerdict:
    metric: str
    sandbox: float | None
    reference: float | None
    relative_error: float | None
    tolerance: float
    verdict: str  # within_tolerance | out_of_tolerance | no_data


@dataclass(frozen=True)
class CalibrationReport:
    schema_version: str
    status: str
    metrics: tuple[MetricVerdict, ...]
    sandbox_deals: int
    sandbox_threads: int


def calibrate_episode(
    episode: MarketEpisodeResult,
    *,
    reference: Mapping[str, Any],
    tolerance: float = 0.20,
    output_path: str | Path | None = None,
) -> CalibrationReport:
    """Compare a market episode's distributions to a reference.

    ``reference`` provides ``mean_clearing_price``, ``mean_rounds``, and
    ``deal_rate``. Each sandbox metric is within tolerance if its relative
    error against the reference is at or below ``tolerance``.
    """

    deal_threads = [
        t for t in episode.threads if t["status"] == "deal" and t["deal_price"] is not None
    ]
    resolved = [
        t
        for t in episode.threads
        if t["status"] in {"deal", "rejected", "timeout", "ghosted"}
    ]
    sandbox_clearing = (
        mean(float(t["deal_price"]) for t in deal_threads) if deal_threads else None
    )
    round_values = [
        float(t["completed_turns"])
        for t in deal_threads
        if t.get("completed_turns") is not None
    ]
    sandbox_rounds = mean(round_values) if round_values else None
    sandbox_deal_rate = (len(deal_threads) / len(resolved)) if resolved else None

    metrics = (
        _verdict(
            "mean_clearing_price",
            sandbox_clearing,
            reference.get("mean_clearing_price"),
            tolerance,
        ),
        _verdict(
            "mean_rounds",
            sandbox_rounds,
            reference.get("mean_rounds"),
            tolerance,
        ),
        _verdict(
            "deal_rate",
            sandbox_deal_rate,
            reference.get("deal_rate"),
            tolerance,
        ),
    )
    evaluated = [m for m in metrics if m.verdict != "no_data"]
    if not evaluated:
        status = "no_data"
    elif all(m.verdict == "within_tolerance" for m in evaluated):
        status = "calibrated"
    else:
        status = "off"

    report = CalibrationReport(
        schema_version=MARKET_CALIBRATION_SCHEMA_VERSION,
        status=status,
        metrics=metrics,
        sandbox_deals=len(deal_threads),
        sandbox_threads=len(episode.threads),
    )
    if output_path is not None:
        write_json(Path(output_path), to_jsonable(report))
    return report


def load_reference(path: str | Path) -> Mapping[str, Any]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, Mapping):
        raise CalibrationError(f"{path}: expected a JSON object reference")
    return data


def reference_from_sold_comps(
    *,
    prices: Sequence[float],
    mean_rounds: float,
    deal_rate: float,
) -> Mapping[str, Any]:
    """Build a reference from real sold-comps prices and observed stats."""

    if not prices:
        raise CalibrationError("prices: expected at least one sold price")
    return {
        "mean_clearing_price": round(mean(prices), 2),
        "mean_rounds": mean_rounds,
        "deal_rate": deal_rate,
    }


def _verdict(
    metric: str,
    sandbox: float | None,
    reference: Any,
    tolerance: float,
) -> MetricVerdict:
    if sandbox is None or reference is None:
        return MetricVerdict(
            metric=metric,
            sandbox=sandbox,
            reference=float(reference) if reference is not None else None,
            relative_error=None,
            tolerance=tolerance,
            verdict="no_data",
        )
    reference = float(reference)
    denom = abs(reference) if reference else 1.0
    relative_error = round(abs(sandbox - reference) / denom, 4)
    verdict = (
        "within_tolerance" if relative_error <= tolerance else "out_of_tolerance"
    )
    return MetricVerdict(
        metric=metric,
        sandbox=round(sandbox, 4),
        reference=round(reference, 4),
        relative_error=relative_error,
        tolerance=tolerance,
        verdict=verdict,
    )
