"""Seller reputation: a public, noisy bargaining signal.

Unlike the hidden condition (see ``opennego.quality``), reputation is public —
both sides see a seller's feedback band — but it is *noisy*: at the same price a
low-reputation seller carries return/dispute risk the buyer must price in. This
module is the single source of truth for the band vocabulary and its risk
weight, shared by the eBay adapter, the scenario layer, the scoring, and the
skill drills.
"""

from __future__ import annotations

# Bands follow the eBay feedback vocabulary (see ``band_from_feedback_pct``).
REPUTATION_BANDS = ("high", "medium", "low", "unknown")

# Realized-value haircut by band: a low-reputation seller is a worse deal at the
# same price because of return/dispute risk. ``unknown`` sits between medium and
# low — the absence of a track record is itself a mild risk.
_REPUTATION_RISK = {"high": 0.0, "medium": 0.06, "low": 0.18, "unknown": 0.10}


def reputation_risk(band: str | None) -> float:
    """Realized-value risk weight in [0, 1) for a reputation band.

    Unknown or unrecognized bands fall back to the ``unknown`` weight, so any
    scenario yields a usable haircut.
    """

    if not band:
        return _REPUTATION_RISK["unknown"]
    return _REPUTATION_RISK.get(str(band).strip().lower(), _REPUTATION_RISK["unknown"])


def band_from_feedback_pct(feedback_pct: float | None) -> str:
    """Map an eBay-style positive-feedback percentage to a reputation band.

    Thresholds mirror the eBay Browse adapter: >=99 high, >=95 medium, else
    low; ``None`` is unknown.
    """

    if feedback_pct is None:
        return "unknown"
    try:
        score = float(feedback_pct)
    except (TypeError, ValueError):
        return "unknown"
    if score >= 99.0:
        return "high"
    if score >= 95.0:
        return "medium"
    return "low"


def normalize_band(band: str | None) -> str:
    """Coerce an arbitrary band string to a known band (default ``unknown``)."""

    if not band:
        return "unknown"
    candidate = str(band).strip().lower()
    return candidate if candidate in REPUTATION_BANDS else "unknown"
