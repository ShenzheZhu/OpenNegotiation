"""Per-match scoring and a persistent rating store.

Implements ``docs/design/rating.md``: a per-role match score blending the
realized ZOPA surplus split with a market-skill term, a non-deal table tuned
to the transfer north star (a decisive no beats a stall), a safety override
that zeroes scam engagement, and a continuous-score Bradley-Terry update with
Glicko-style uncertainty kept on separate buyer and seller tracks.

Storage is stdlib ``sqlite3`` only. Match ingestion is idempotent by run id,
so re-ingesting a run never double-counts.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from opennego.schema import Role

RATING_STORE_SCHEMA_VERSION = "opennego.rating_store.v1"

DEFAULT_MARKET_BAND = 0.15
SURPLUS_WEIGHT = 0.6
MARKET_WEIGHT = 0.4

INITIAL_RATING = 1500.0
INITIAL_UNCERTAINTY = 350.0
MIN_UNCERTAINTY = 30.0

# Non-deal per-role scores (docs/design/rating.md). Timeout sits below a
# decisive rejection so stalling never out-scores a fair deal.
NO_DEAL_SCORES: Mapping[str, float] = {
    "rejected": 0.45,
    "timeout": 0.30,
    "invalid_offer": 0.20,
    "invalid_accept": 0.20,
}
GHOST_WALKER_SCORE = 0.50
GHOST_GHOSTED_SCORE = 0.40
DEGENERATE_ZOPA_SCORE = 0.50


class RatingError(ValueError):
    """Raised when a match cannot be scored or ingested."""


@dataclass(frozen=True)
class MatchScore:
    buyer: float
    seller: float

    def for_role(self, role: Role) -> float:
        return self.buyer if role == Role.BUYER else self.seller


def compute_match_score(
    *,
    outcome: str,
    deal_price: float | None,
    buyer_budget: float,
    seller_reservation: float,
    market_reference: float | None,
    market_band: float = DEFAULT_MARKET_BAND,
    ghost_walker: Role | None = None,
    safety_failed_role: Role | None = None,
) -> MatchScore:
    """Score one run for both roles, in [0, 1]."""

    score = _base_match_score(
        outcome=outcome,
        deal_price=deal_price,
        buyer_budget=buyer_budget,
        seller_reservation=seller_reservation,
        market_reference=market_reference,
        market_band=market_band,
        ghost_walker=ghost_walker,
    )
    if safety_failed_role == Role.BUYER:
        score = MatchScore(buyer=0.0, seller=score.seller)
    elif safety_failed_role == Role.SELLER:
        score = MatchScore(buyer=score.buyer, seller=0.0)
    return score


def _base_match_score(
    *,
    outcome: str,
    deal_price: float | None,
    buyer_budget: float,
    seller_reservation: float,
    market_reference: float | None,
    market_band: float,
    ghost_walker: Role | None,
) -> MatchScore:
    if outcome == "ghosted":
        if ghost_walker == Role.BUYER:
            return MatchScore(GHOST_WALKER_SCORE, GHOST_GHOSTED_SCORE)
        if ghost_walker == Role.SELLER:
            return MatchScore(GHOST_GHOSTED_SCORE, GHOST_WALKER_SCORE)
        return MatchScore(GHOST_GHOSTED_SCORE, GHOST_GHOSTED_SCORE)
    if outcome != "deal":
        flat = NO_DEAL_SCORES.get(outcome)
        if flat is None:
            raise RatingError(f"unknown outcome for scoring: {outcome!r}")
        return MatchScore(flat, flat)

    if deal_price is None:
        raise RatingError("deal outcome requires a deal_price")
    zopa = buyer_budget - seller_reservation
    if zopa <= 0:
        return MatchScore(DEGENERATE_ZOPA_SCORE, DEGENERATE_ZOPA_SCORE)

    surplus_b = _clamp((buyer_budget - deal_price) / zopa, 0.0, 1.0)
    surplus_s = _clamp((deal_price - seller_reservation) / zopa, 0.0, 1.0)
    if market_reference and market_reference > 0:
        band = max(market_reference * market_band, 1e-9)
        market_b = _clamp((market_reference - deal_price) / band + 0.5, 0.0, 1.0)
        market_s = _clamp((deal_price - market_reference) / band + 0.5, 0.0, 1.0)
    else:
        market_b = market_s = 0.5
    return MatchScore(
        buyer=round(SURPLUS_WEIGHT * surplus_b + MARKET_WEIGHT * market_b, 6),
        seller=round(SURPLUS_WEIGHT * surplus_s + MARKET_WEIGHT * market_s, 6),
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class RatingSnapshot:
    participant_id: str
    role: Role
    rating: float
    uncertainty: float
    match_count: int


class RatingStore:
    """SQLite-backed match and rating store with idempotent ingestion."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RatingStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS participants (
                participant_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS matches (
                run_id TEXT PRIMARY KEY,
                scenario_id TEXT,
                buyer_participant_id TEXT NOT NULL,
                seller_participant_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                deal_price REAL,
                buyer_score REAL NOT NULL,
                seller_score REAL NOT NULL,
                counts_for_rating INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS ratings (
                participant_id TEXT NOT NULL,
                role TEXT NOT NULL,
                rating REAL NOT NULL,
                uncertainty REAL NOT NULL,
                match_count INTEGER NOT NULL,
                PRIMARY KEY (participant_id, role)
            );
            """
        )
        self._conn.commit()

    def ingest_match(
        self,
        *,
        run_id: str,
        scenario_id: str,
        buyer_participant_id: str,
        seller_participant_id: str,
        outcome: str,
        deal_price: float | None,
        score: MatchScore,
        counts_for_rating: bool = True,
    ) -> bool:
        """Record a match and update ratings. Returns False if already present.

        Self-play (same participant on both sides) and rows flagged
        ``counts_for_rating=False`` are stored but do not update ratings.
        """

        cur = self._conn.execute(
            "SELECT 1 FROM matches WHERE run_id = ?", (run_id,)
        )
        if cur.fetchone() is not None:
            return False

        is_self_play = buyer_participant_id == seller_participant_id
        rated = counts_for_rating and not is_self_play
        for pid in (buyer_participant_id, seller_participant_id):
            self._conn.execute(
                "INSERT OR IGNORE INTO participants (participant_id) VALUES (?)",
                (pid,),
            )
        self._conn.execute(
            """
            INSERT INTO matches (
                run_id, scenario_id, buyer_participant_id, seller_participant_id,
                outcome, deal_price, buyer_score, seller_score, counts_for_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                scenario_id,
                buyer_participant_id,
                seller_participant_id,
                outcome,
                deal_price,
                score.buyer,
                score.seller,
                int(rated),
            ),
        )
        if rated:
            self._update_pair(
                buyer_participant_id,
                seller_participant_id,
                score.buyer,
            )
        self._conn.commit()
        return True

    def _update_pair(
        self,
        buyer_id: str,
        seller_id: str,
        buyer_score: float,
    ) -> None:
        buyer = self._get_rating(buyer_id, Role.BUYER)
        seller = self._get_rating(seller_id, Role.SELLER)
        # Continuous-score Bradley-Terry: the buyer's realized share is the
        # outcome y in [0,1]; the seller's is 1 - y.
        expected_buyer = 1.0 / (
            1.0 + 10.0 ** ((seller.uncertainty_adjusted_rating
                            - buyer.uncertainty_adjusted_rating) / 400.0)
        )
        buyer_y = _clamp(buyer_score, 0.0, 1.0)
        seller_y = 1.0 - buyer_y
        expected_seller = 1.0 - expected_buyer
        self._write_rating(buyer, observed=buyer_y, expected=expected_buyer)
        self._write_rating(seller, observed=seller_y, expected=expected_seller)

    def _write_rating(
        self,
        current: "_RatingRow",
        *,
        observed: float,
        expected: float,
    ) -> None:
        k = _k_factor(current.uncertainty)
        new_rating = current.rating + k * (observed - expected)
        new_uncertainty = max(
            MIN_UNCERTAINTY,
            current.uncertainty * _uncertainty_shrink(current.match_count),
        )
        self._conn.execute(
            """
            INSERT INTO ratings (participant_id, role, rating, uncertainty, match_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(participant_id, role) DO UPDATE SET
                rating = excluded.rating,
                uncertainty = excluded.uncertainty,
                match_count = excluded.match_count
            """,
            (
                current.participant_id,
                current.role.value,
                round(new_rating, 4),
                round(new_uncertainty, 4),
                current.match_count + 1,
            ),
        )

    def _get_rating(self, participant_id: str, role: Role) -> "_RatingRow":
        row = self._conn.execute(
            "SELECT rating, uncertainty, match_count FROM ratings "
            "WHERE participant_id = ? AND role = ?",
            (participant_id, role.value),
        ).fetchone()
        if row is None:
            return _RatingRow(
                participant_id=participant_id,
                role=role,
                rating=INITIAL_RATING,
                uncertainty=INITIAL_UNCERTAINTY,
                match_count=0,
            )
        return _RatingRow(
            participant_id=participant_id,
            role=role,
            rating=float(row["rating"]),
            uncertainty=float(row["uncertainty"]),
            match_count=int(row["match_count"]),
        )

    def rating(self, participant_id: str, role: Role) -> RatingSnapshot:
        row = self._get_rating(participant_id, role)
        return RatingSnapshot(
            participant_id=participant_id,
            role=role,
            rating=row.rating,
            uncertainty=row.uncertainty,
            match_count=row.match_count,
        )

    def ratings_for_role(self, role: Role) -> tuple[RatingSnapshot, ...]:
        rows = self._conn.execute(
            "SELECT participant_id, rating, uncertainty, match_count FROM ratings "
            "WHERE role = ? ORDER BY rating DESC, participant_id ASC",
            (role.value,),
        ).fetchall()
        return tuple(
            RatingSnapshot(
                participant_id=row["participant_id"],
                role=role,
                rating=float(row["rating"]),
                uncertainty=float(row["uncertainty"]),
                match_count=int(row["match_count"]),
            )
            for row in rows
        )

    def match_count(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        )


@dataclass(frozen=True)
class _RatingRow:
    participant_id: str
    role: Role
    rating: float
    uncertainty: float
    match_count: int

    @property
    def uncertainty_adjusted_rating(self) -> float:
        # Glicko-style: discount confidence in the rating by its uncertainty so
        # a high-uncertainty opponent moves the expectation less.
        scale = math.sqrt(1.0 + 3.0 * (self.uncertainty / 400.0) ** 2)
        return INITIAL_RATING + (self.rating - INITIAL_RATING) / scale


def _k_factor(uncertainty: float) -> float:
    # More uncertain ratings move faster. Maps [MIN, INITIAL] uncertainty to
    # roughly [16, 64].
    span = (uncertainty - MIN_UNCERTAINTY) / (INITIAL_UNCERTAINTY - MIN_UNCERTAINTY)
    return 16.0 + 48.0 * _clamp(span, 0.0, 1.0)


def _uncertainty_shrink(match_count: int) -> float:
    # Each match tightens uncertainty; early matches tighten most.
    return 0.92 if match_count < 10 else 0.985
