import { useEffect, useState } from "react";
import {
  EuiPanel,
  EuiText,
  EuiSpacer,
  EuiButton,
  EuiCallOut,
  EuiBasicTable,
  EuiFlexGroup,
  EuiFlexItem,
  EuiBadge,
} from "@elastic/eui";
import { ratingsApi, type RatingEntry, type RatingLeaderboard } from "../api/client";

export function RatingsView({ agentId }: { agentId: string | null }) {
  const [board, setBoard] = useState<RatingLeaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    ratingsApi
      .get()
      .then(setBoard)
      .catch((e) => setError((e as Error).message));
  };
  useEffect(load, []);

  const columns = [
    { field: "rank", name: "#", width: "60px" },
    {
      field: "participant_id",
      name: "Participant",
      render: (id: string) =>
        id === agentId ? <EuiBadge color="primary">{id} (you)</EuiBadge> : id,
    },
    {
      name: "Rating",
      render: (e: RatingEntry) => `${e.rating.toFixed(0)} ± ${e.uncertainty.toFixed(0)}`,
    },
    { field: "match_count", name: "Matches", width: "100px" },
  ];

  const table = (title: string, rows: RatingEntry[]) => (
    <EuiFlexItem>
      <EuiText>
        <h3>{title}</h3>
      </EuiText>
      <EuiSpacer size="s" />
      {rows.length ? (
        <EuiBasicTable
          items={rows.map((r) => ({ ...r, key: r.participant_id }))}
          columns={columns}
          rowProps={(r: RatingEntry) =>
            r.participant_id === agentId ? { style: { background: "#e6f0ff" } } : {}
          }
        />
      ) : (
        <EuiText color="subdued">
          <p>No rated participants yet. Run some matches.</p>
        </EuiText>
      )}
    </EuiFlexItem>
  );

  return (
    <EuiPanel>
      <EuiFlexGroup alignItems="center">
        <EuiFlexItem>
          <EuiText>
            <h2>Ratings</h2>
            <p>{board ? `${board.match_count} matches recorded` : "Loading…"}</p>
          </EuiText>
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiButton onClick={load}>Refresh</EuiButton>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer />
      {error && <EuiCallOut title={error} color="danger" iconType="alert" />}
      {board && (
        <EuiFlexGroup>
          {table("Buyer track", board.buyer_track)}
          {table("Seller track", board.seller_track)}
        </EuiFlexGroup>
      )}
    </EuiPanel>
  );
}
