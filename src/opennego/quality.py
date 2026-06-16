"""Condition-to-quality mapping for the information-asymmetry track.

A negotiation runs on one public claim (``Product.condition``) and, when the
scenario sets it, a hidden ``seller_true_quality``. Both live on the same
[0, 1] axis so the buyer's inspect tool can report an estimate the buyer can
compare against the claim. This module is the deterministic bridge from an
eBay-style condition string to that axis; it is the buyer's public reference
point and carries no private information.
"""

from __future__ import annotations

# Ordered most-to-least specific: the first band whose keyword appears in the
# (lowercased) condition wins, so refurbished bands resolve before the generic
# "new" band (note "renewed" contains the substring "new"), and "very good"
# resolves before "good". Bands follow the eBay item-condition vocabulary;
# values are deliberate, documented points on the [0, 1] axis.
_CONDITION_BANDS: tuple[tuple[tuple[str, ...], float], ...] = (
    (("for parts", "not working", "spares", "salvage", "broken"), 0.15),
    (("acceptable", "fair", "poor", "heavily used"), 0.45),
    (("certified refurbished",), 0.88),
    (("refurbished", "renewed", "reconditioned"), 0.8),
    (("new with tags", "brand new"), 1.0),
    (("new without tags", "new other", "new (other)"), 0.95),
    (("like new", "open box", "open-box", "mint"), 0.9),
    (("excellent",), 0.82),
    (("very good",), 0.72),
    (("good",), 0.6),
    (("used", "pre-owned", "preowned", "second hand", "second-hand"), 0.6),
    (("new",), 1.0),
)

DEFAULT_QUALITY = 0.5


def condition_to_quality(condition: str | None) -> float:
    """Map a public condition claim to a quality estimate in [0, 1].

    Unknown or empty conditions fall back to ``DEFAULT_QUALITY`` (a neutral
    midpoint), so any product record yields a usable reference point.
    """

    if not condition:
        return DEFAULT_QUALITY
    text = condition.strip().lower()
    if not text:
        return DEFAULT_QUALITY
    for keywords, value in _CONDITION_BANDS:
        if any(keyword in text for keyword in keywords):
            return value
    return DEFAULT_QUALITY
