"""Buyer-side quality inspection tool.

The seller knows the item's true condition; the buyer only sees a public
claim. This tool lets the buyer *elicit* hidden quality at the cost of a turn:
each call returns a noisy private estimate of the true quality on the [0, 1]
axis. Repeating the inspection draws another independent sample and tightens
the reported interval, so information has a real per-turn price.

The tool holds the true quality internally (captured at construction from the
scenario) and never echoes it back — only the noisy estimate crosses the
boundary, and the environment marks the result private to the caller. This
preserves the same red line as the seller's private state: the buyer never
sees the raw truth, even when calling the tool that depends on it.
"""

from __future__ import annotations

import hashlib
from typing import Mapping

from opennego.quality import condition_to_quality
from opennego.schema import AgentContext, Scenario

DEFAULT_NOISE_STD = 0.12


def _unit_sample(seed: str) -> float:
    """Deterministic pseudo-random draw in [0, 1) from a stable hash."""

    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


class QualityInspectionTool:
    """Return a noisy, private estimate of an item's true quality.

    Estimates are deterministic given ``base_seed`` and the call index, so a
    run replays identically. The running mean over repeated calls converges
    toward the truth and the reported half-width shrinks with the sample count.
    """

    name = "inspect"
    description = (
        "Inspect the item for a noisy private estimate of its true quality "
        "(0-1). Costs a turn; repeat to tighten the estimate."
    )

    def __init__(
        self,
        *,
        true_quality: float,
        claimed_quality: float,
        base_seed: int = 0,
        noise_std: float = DEFAULT_NOISE_STD,
        scenario_key: str = "",
    ) -> None:
        self.true_quality = _clamp_unit(true_quality)
        self.claimed_quality = _clamp_unit(claimed_quality)
        self.base_seed = base_seed
        self.noise_std = noise_std
        self.scenario_key = scenario_key
        # Per-role call state so repeated inspections refine a running estimate.
        self._calls: dict[str, int] = {}

    @classmethod
    def from_scenario(
        cls,
        scenario: Scenario,
        *,
        base_seed: int = 0,
        noise_std: float = DEFAULT_NOISE_STD,
    ) -> "QualityInspectionTool":
        claimed = condition_to_quality(scenario.product.condition)
        # No hidden defect declared -> the item is "as described".
        true_quality = (
            scenario.seller_true_quality
            if scenario.seller_true_quality is not None
            else claimed
        )
        return cls(
            true_quality=true_quality,
            claimed_quality=claimed,
            base_seed=base_seed,
            noise_std=noise_std,
            scenario_key=scenario.product.id,
        )

    def call(
        self,
        arguments: Mapping[str, object],
        context: AgentContext | None,
    ) -> Mapping[str, object]:
        role_key = context.role.value if context is not None else "anonymous"
        index = self._calls.get(role_key, 0) + 1
        self._calls[role_key] = index

        # Accumulate every sample drawn so far for this caller so the estimate
        # is the running mean — deterministic in the call index, not the order
        # of unrelated tool calls.
        samples = [
            _clamp_unit(
                self.true_quality
                + (
                    _unit_sample(f"{self.scenario_key}:{self.base_seed}:{role_key}:{i}")
                    * 2.0
                    - 1.0
                )
                * self.noise_std
            )
            for i in range(1, index + 1)
        ]
        estimate = sum(samples) / len(samples)
        # Heuristic confidence band that shrinks as more samples are taken.
        half_width = self.noise_std / (index ** 0.5)
        below_claim = self.claimed_quality - estimate
        return {
            "ok": True,
            "claimed_quality": round(self.claimed_quality, 3),
            "estimate_quality": round(estimate, 3),
            "estimate_low": round(_clamp_unit(estimate - half_width), 3),
            "estimate_high": round(_clamp_unit(estimate + half_width), 3),
            "samples_taken": index,
            "noise_std": self.noise_std,
            "below_claim": round(below_claim, 3),
            "note": (
                "Noisy private estimate of true condition on a 0-1 quality "
                "axis. A positive below_claim means the item looks worse than "
                "the public claim. Inspect again to tighten the interval."
            ),
        }
