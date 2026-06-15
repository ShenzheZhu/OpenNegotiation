"""Machine-readable leaderboard aggregation for benchmark artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from opennego.artifacts import (
    ArtifactValidationError,
    load_manifest,
    load_metric_report,
)
from opennego.artifacts import write_json
from opennego.rating import RatingStore
from opennego.schema import Role

LEADERBOARD_SCHEMA_VERSION = "opennego.leaderboard.v1"
LEADERBOARD_V2_SCHEMA_VERSION = "opennego.leaderboard.v2"


@dataclass(frozen=True)
class LeaderboardRunRow:
    rank: int
    run_id: str
    scenario_id: str
    tool_regime_id: str
    score: float
    outcome: str
    deal_price: float | None
    buyer_participant_id: str
    seller_participant_id: str
    metrics: Mapping[str, float]


@dataclass(frozen=True)
class RoleTrackEntry:
    rank: int
    role: str
    participant_id: str
    run_count: int
    average_score: float
    deal_rate: float
    transaction_completion_rate: float
    average_normalized_market_gap: float
    tool_failure_rate: float
    average_role_value_vs_market_reference: float


@dataclass(frozen=True)
class ParticipantSummary:
    rank: int
    participant_id: str
    roles: tuple[str, ...]
    role_coverage: float
    unique_run_count: int
    role_appearance_count: int
    average_score: float
    coverage_adjusted_score: float
    buyer_average_score: float | None
    seller_average_score: float | None
    balanced_average_score: float | None


@dataclass(frozen=True)
class LeaderboardSummary:
    schema_version: str
    input_dir: str
    run_count: int
    participant_summaries: tuple[ParticipantSummary, ...]
    role_tracks: tuple[RoleTrackEntry, ...]
    runs: tuple[LeaderboardRunRow, ...]


def build_leaderboard(input_dir: str | Path) -> LeaderboardSummary:
    """Aggregate benchmark artifact directories into leaderboard rows."""

    base = Path(input_dir)
    loaded = _load_runs(base)
    if not loaded:
        raise ValueError(f"{base}: no benchmark run artifacts found")
    run_rows = tuple(
        LeaderboardRunRow(
            rank=index,
            run_id=item["run_id"],
            scenario_id=item["scenario_id"],
            tool_regime_id=item["tool_regime_id"],
            score=item["score"],
            outcome=item["outcome"],
            deal_price=item["deal_price"],
            buyer_participant_id=item["buyer_participant_id"],
            seller_participant_id=item["seller_participant_id"],
            metrics=item["metrics"],
        )
        for index, item in enumerate(
            sorted(loaded, key=lambda item: item["score"], reverse=True),
            start=1,
        )
    )
    role_tracks = _role_tracks(run_rows)
    return LeaderboardSummary(
        schema_version=LEADERBOARD_SCHEMA_VERSION,
        input_dir=str(base),
        run_count=len(run_rows),
        participant_summaries=_participant_summaries(role_tracks, run_rows),
        role_tracks=role_tracks,
        runs=run_rows,
    )


def write_leaderboard(input_dir: str | Path, output_path: str | Path) -> Path:
    """Write a versioned leaderboard summary JSON artifact."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, build_leaderboard(input_dir))
    return path


@dataclass(frozen=True)
class RatingLeaderboardEntry:
    rank: int
    participant_id: str
    rating: float
    uncertainty: float
    match_count: int


@dataclass(frozen=True)
class RatingLeaderboard:
    schema_version: str
    store_path: str
    match_count: int
    buyer_track: tuple[RatingLeaderboardEntry, ...]
    seller_track: tuple[RatingLeaderboardEntry, ...]


def build_rating_leaderboard(store: RatingStore) -> RatingLeaderboard:
    """Rank participants by buyer-track and seller-track rating."""

    return RatingLeaderboard(
        schema_version=LEADERBOARD_V2_SCHEMA_VERSION,
        store_path=store.path,
        match_count=store.match_count(),
        buyer_track=_rating_track(store, Role.BUYER),
        seller_track=_rating_track(store, Role.SELLER),
    )


def write_rating_leaderboard(
    store_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Write an opennego.leaderboard.v2 rating leaderboard from a store."""

    store = RatingStore(store_path)
    try:
        leaderboard = build_rating_leaderboard(store)
    finally:
        store.close()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, leaderboard)
    return path


def _rating_track(store: RatingStore, role: Role) -> tuple[RatingLeaderboardEntry, ...]:
    return tuple(
        RatingLeaderboardEntry(
            rank=index,
            participant_id=snapshot.participant_id,
            rating=snapshot.rating,
            uncertainty=snapshot.uncertainty,
            match_count=snapshot.match_count,
        )
        for index, snapshot in enumerate(store.ratings_for_role(role), start=1)
    )


def render_rating_leaderboard_html(leaderboard: RatingLeaderboard) -> str:
    """Render a standalone HTML page with the buyer/seller rating tables."""

    def _rows(track: Sequence[RatingLeaderboardEntry]) -> str:
        if not track:
            return '<tr><td colspan="4">No rated participants yet.</td></tr>'
        return "\n".join(
            "<tr>"
            f"<td>{entry.rank}</td>"
            f"<td>{_escape(entry.participant_id)}</td>"
            f"<td>{entry.rating:.1f} &plusmn; {entry.uncertainty:.0f}</td>"
            f"<td>{entry.match_count}</td>"
            "</tr>"
            for entry in track
        )

    def _table(title: str, track: Sequence[RatingLeaderboardEntry]) -> str:
        return (
            f"<h2>{_escape(title)}</h2>"
            "<table><thead><tr><th>Rank</th><th>Participant</th>"
            "<th>Rating</th><th>Matches</th></tr></thead>"
            f"<tbody>{_rows(track)}</tbody></table>"
        )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>OpenNegotiation Ratings</title></head><body>"
        "<h1>OpenNegotiation rating leaderboard</h1>"
        f"<p>Schema {_escape(leaderboard.schema_version)}; "
        f"{leaderboard.match_count} matches.</p>"
        f"{_table('Buyer track', leaderboard.buyer_track)}"
        f"{_table('Seller track', leaderboard.seller_track)}"
        "</body></html>\n"
    )


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _load_runs(base: Path) -> list[dict]:
    candidates = [base] if (base / "metrics.json").exists() else sorted(base.iterdir())
    rows: list[dict] = []
    seen_run_ids: dict[str, Path] = {}
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        try:
            manifest = load_manifest(candidate / "manifest.json")
            metrics_report = load_metric_report(candidate / "metrics.json")
        except (OSError, ArtifactValidationError, ValueError):
            continue
        previous = seen_run_ids.get(manifest.run_id)
        if previous is not None:
            raise ValueError(
                f"{base}: duplicate benchmark run_id {manifest.run_id!r} in "
                f"{previous} and {candidate}"
            )
        seen_run_ids[manifest.run_id] = candidate
        metrics = dict(metrics_report.metrics)
        rows.append(
            {
                "run_id": manifest.run_id,
                "scenario_id": metrics_report.scenario_id,
                "tool_regime_id": _tool_regime_id(manifest.tool_regime),
                "score": _score(metrics),
                "outcome": metrics_report.outcome,
                "deal_price": metrics_report.deal_price,
                "buyer_participant_id": _participant_id(manifest, "buyer"),
                "seller_participant_id": _participant_id(manifest, "seller"),
                "metrics": metrics,
            }
        )
    return rows


def _participant_id(manifest, role: str) -> str:
    models = manifest.models
    if isinstance(models, Mapping) and models.get(role):
        return str(models[role])
    agents = manifest.agents
    agent = agents.get(role) if isinstance(agents, Mapping) else None
    if isinstance(agent, Mapping):
        participant_id = agent.get("participant_id")
        if isinstance(participant_id, str) and participant_id:
            return participant_id
        kind = str(agent.get("kind", "agent"))
        name = str(agent.get("name", kind))
        return f"{kind}:{name}"
    return f"unknown_{role}"


def _tool_regime_id(tool_regime: Mapping[str, object]) -> str:
    return str(tool_regime.get("id", "unknown"))


def _score(metrics: Mapping[str, float]) -> float:
    deal = metrics.get("deal_rate", 0.0)
    tx = metrics.get("transaction_completed_rate", 0.0)
    gap = metrics.get("normalized_market_gap", 0.0)
    gap_component = max(0.0, 1.0 - min(gap, 2.0) / 2.0)
    tool_calls = metrics.get("tool_call_count", 0.0)
    failures = metrics.get("tool_failure_count", 0.0)
    tool_quality = 1.0 if tool_calls == 0 else max(0.0, 1.0 - failures / tool_calls)
    return round(
        100 * (0.35 * deal + 0.25 * tx + 0.25 * gap_component + 0.15 * tool_quality),
        1,
    )


def _role_tracks(rows: Sequence[LeaderboardRunRow]) -> tuple[RoleTrackEntry, ...]:
    entries = []
    for role in ("buyer", "seller"):
        by_participant: dict[str, list[LeaderboardRunRow]] = {}
        for row in rows:
            participant_id = (
                row.buyer_participant_id if role == "buyer" else row.seller_participant_id
            )
            by_participant.setdefault(participant_id, []).append(row)
        role_entries = [
            _role_track_entry(role, participant_id, participant_rows)
            for participant_id, participant_rows in by_participant.items()
        ]
        entries.extend(
            entry
            for _, entry in enumerate(
                sorted(
                    role_entries,
                    key=lambda item: (
                        item.role,
                        -item.average_score,
                        item.participant_id,
                    ),
                ),
                start=1,
            )
        )
    ranked = []
    for role in ("buyer", "seller"):
        role_entries = [
            entry for entry in entries if entry.role == role
        ]
        for rank, entry in enumerate(role_entries, start=1):
            ranked.append(
                RoleTrackEntry(
                    rank=rank,
                    role=entry.role,
                    participant_id=entry.participant_id,
                    run_count=entry.run_count,
                    average_score=entry.average_score,
                    deal_rate=entry.deal_rate,
                    transaction_completion_rate=entry.transaction_completion_rate,
                    average_normalized_market_gap=entry.average_normalized_market_gap,
                    tool_failure_rate=entry.tool_failure_rate,
                    average_role_value_vs_market_reference=(
                        entry.average_role_value_vs_market_reference
                    ),
                )
            )
    return tuple(ranked)


def _participant_summaries(
    role_tracks: Sequence[RoleTrackEntry],
    rows: Sequence[LeaderboardRunRow],
) -> tuple[ParticipantSummary, ...]:
    by_participant: dict[str, dict[str, RoleTrackEntry]] = {}
    for entry in role_tracks:
        by_participant.setdefault(entry.participant_id, {})[entry.role] = entry

    run_ids_by_participant: dict[str, set[str]] = {}
    for row in rows:
        run_ids_by_participant.setdefault(row.buyer_participant_id, set()).add(row.run_id)
        run_ids_by_participant.setdefault(row.seller_participant_id, set()).add(row.run_id)

    summaries = [
        _participant_summary(
            participant_id=participant_id,
            role_entries=role_entries,
            unique_run_count=len(run_ids_by_participant.get(participant_id, set())),
        )
        for participant_id, role_entries in by_participant.items()
    ]
    ranked = sorted(
        summaries,
        key=lambda item: (
            -item.coverage_adjusted_score,
            -item.role_coverage,
            -item.average_score,
            item.participant_id,
        ),
    )
    return tuple(
        ParticipantSummary(
            rank=rank,
            participant_id=entry.participant_id,
            roles=entry.roles,
            role_coverage=entry.role_coverage,
            unique_run_count=entry.unique_run_count,
            role_appearance_count=entry.role_appearance_count,
            average_score=entry.average_score,
            coverage_adjusted_score=entry.coverage_adjusted_score,
            buyer_average_score=entry.buyer_average_score,
            seller_average_score=entry.seller_average_score,
            balanced_average_score=entry.balanced_average_score,
        )
        for rank, entry in enumerate(ranked, start=1)
    )


def _participant_summary(
    *,
    participant_id: str,
    role_entries: Mapping[str, RoleTrackEntry],
    unique_run_count: int,
) -> ParticipantSummary:
    roles = tuple(role for role in ("buyer", "seller") if role in role_entries)
    role_scores = [role_entries[role].average_score for role in roles]
    average_score = _average(role_scores)
    role_coverage = round(len(roles) / 2, 4)
    return ParticipantSummary(
        rank=0,
        participant_id=participant_id,
        roles=roles,
        role_coverage=role_coverage,
        unique_run_count=unique_run_count,
        role_appearance_count=sum(role_entries[role].run_count for role in roles),
        average_score=average_score,
        coverage_adjusted_score=round(average_score * role_coverage, 4),
        buyer_average_score=_role_average(role_entries, "buyer"),
        seller_average_score=_role_average(role_entries, "seller"),
        balanced_average_score=average_score if len(roles) == 2 else None,
    )


def _role_average(
    role_entries: Mapping[str, RoleTrackEntry],
    role: str,
) -> float | None:
    entry = role_entries.get(role)
    if entry is None:
        return None
    return entry.average_score


def _role_track_entry(
    role: str,
    participant_id: str,
    rows: Sequence[LeaderboardRunRow],
) -> RoleTrackEntry:
    return RoleTrackEntry(
        rank=0,
        role=role,
        participant_id=participant_id,
        run_count=len(rows),
        average_score=_average(row.score for row in rows),
        deal_rate=_average(row.metrics.get("deal_rate", 0.0) for row in rows),
        transaction_completion_rate=_average(
            row.metrics.get("transaction_completed_rate", 0.0) for row in rows
        ),
        average_normalized_market_gap=_average(
            row.metrics.get("normalized_market_gap", 0.0) for row in rows
        ),
        tool_failure_rate=_tool_failure_rate(rows),
        average_role_value_vs_market_reference=_role_value(role, rows),
    )


def _average(values) -> float:
    items = [float(value) for value in values]
    if not items:
        return 0.0
    return round(sum(items) / len(items), 4)


def _tool_failure_rate(rows: Sequence[LeaderboardRunRow]) -> float:
    calls = sum(row.metrics.get("tool_call_count", 0.0) for row in rows)
    failures = sum(row.metrics.get("tool_failure_count", 0.0) for row in rows)
    if calls <= 0:
        return 0.0
    return round(failures / calls, 4)


def _role_value(role: str, rows: Sequence[LeaderboardRunRow]) -> float:
    metric_key = (
        "buyer_savings_vs_market_reference"
        if role == "buyer"
        else "seller_revenue_vs_market_reference"
    )
    return _average(row.metrics.get(metric_key, 0.0) for row in rows)
