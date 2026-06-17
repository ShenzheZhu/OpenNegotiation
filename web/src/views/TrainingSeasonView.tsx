import { useState } from "react";
import {
  EuiPanel,
  EuiText,
  EuiSpacer,
  EuiButton,
  EuiCallOut,
  EuiBasicTable,
  EuiBadge,
  EuiFlexGroup,
  EuiFlexItem,
} from "@elastic/eui";
import {
  seasonApi,
  coachApi,
  type TrainingSeason,
  type AggregatedWeakness,
  type CandidateSlateEntry,
} from "../api/client";

const verdictColor = (verdict: string): string =>
  verdict === "improved" ? "success" : verdict === "regressed" ? "danger" : "warning";

export function TrainingSeasonView({ agentId }: { agentId: string | null }) {
  const [season, setSeason] = useState<TrainingSeason | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<string | null>(null);

  const run = () => {
    if (!agentId) return;
    setBusy(true);
    setError(null);
    setApplied(null);
    seasonApi
      .run(agentId, 3)
      .then(setSeason)
      .catch((e) => setError((e as Error).message))
      .finally(() => setBusy(false));
  };

  const apply = (entry: CandidateSlateEntry) => {
    if (!agentId) return;
    setError(null);
    coachApi
      .decide(agentId, entry.candidate_path, "accepted", !entry.generalizes)
      .then((d) => setApplied(`Applied ${entry.candidate_id} (v${d.strategy_version ?? "?"})`))
      .catch((e) => setError((e as Error).message));
  };

  const weaknessColumns = [
    { field: "phase", name: "Phase", width: "110px" },
    { field: "category", name: "Category" },
    { field: "frequency", name: "Freq", width: "70px" },
    {
      name: "Mean score",
      render: (w: AggregatedWeakness) => w.mean_policy_score.toFixed(3),
      width: "110px",
    },
    {
      name: "Priority",
      render: (w: AggregatedWeakness) => w.priority.toFixed(3),
      width: "100px",
    },
  ];

  const slateColumns = [
    { field: "rank", name: "#", width: "50px" },
    {
      name: "Targets",
      render: (e: CandidateSlateEntry) => `${e.phase}/${e.category}`,
    },
    {
      name: "Held-out Δ",
      render: (e: CandidateSlateEntry) => e.heldout_score_delta.toFixed(4),
      width: "110px",
    },
    {
      name: "Verdict",
      render: (e: CandidateSlateEntry) => (
        <EuiBadge color={verdictColor(e.verdict)}>
          {e.verdict}
          {e.candidate_id === season?.recommended_candidate_id ? " ★" : ""}
        </EuiBadge>
      ),
    },
    {
      name: "Apply",
      render: (e: CandidateSlateEntry) => (
        <EuiButton size="s" onClick={() => apply(e)} disabled={!agentId}>
          Apply
        </EuiButton>
      ),
    },
  ];

  return (
    <EuiPanel>
      <EuiFlexGroup alignItems="center">
        <EuiFlexItem>
          <EuiText>
            <h2>Training season</h2>
            <p>
              Spar the whole roster, see where{" "}
              {agentId ? <strong>{agentId}</strong> : "your agent"} loses, and pick a
              held-out-validated fix.
            </p>
          </EuiText>
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiButton onClick={run} isLoading={busy} disabled={!agentId} fill>
            Run season
          </EuiButton>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer />
      {!agentId && (
        <EuiCallOut title="Define and select an agent first" color="warning" iconType="user" />
      )}
      {error && <EuiCallOut title={error} color="danger" iconType="alert" />}
      {applied && <EuiCallOut title={applied} color="success" iconType="check" />}
      {season && (
        <>
          <EuiSpacer />
          <EuiText>
            <p>
              Baseline mean {season.trajectory.baseline_mean_score.toFixed(3)} → best{" "}
              {season.trajectory.best_mean_score.toFixed(3)} (Δ{" "}
              {season.trajectory.delta.toFixed(4)}) over{" "}
              {season.weakness_profile.matches_analyzed} matches.
            </p>
            <h3>Ranked weaknesses</h3>
          </EuiText>
          <EuiSpacer size="s" />
          <EuiBasicTable
            items={season.weakness_profile.weaknesses.map((w, i) => ({ ...w, key: i }))}
            columns={weaknessColumns}
          />
          <EuiSpacer />
          <EuiText>
            <h3>Validated candidate slate</h3>
          </EuiText>
          <EuiSpacer size="s" />
          {season.slate.length ? (
            <EuiBasicTable
              items={season.slate.map((e) => ({ ...e, key: e.candidate_id }))}
              columns={slateColumns}
            />
          ) : (
            <EuiText color="subdued">
              <p>No candidates generated.</p>
            </EuiText>
          )}
        </>
      )}
    </EuiPanel>
  );
}
