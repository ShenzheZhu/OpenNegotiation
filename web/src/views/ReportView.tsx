import { useState } from "react";
import {
  EuiPanel,
  EuiText,
  EuiSpacer,
  EuiCallOut,
  EuiButton,
  EuiBadge,
  EuiBasicTable,
  EuiFlexGroup,
  EuiFlexItem,
  EuiStat,
  EuiCodeBlock,
  EuiHorizontalRule,
  EuiConfirmModal,
} from "@elastic/eui";
import {
  coachApi,
  type BattleReport,
  type EvolveResult,
  type DecisionResult,
} from "../api/client";

const SEVERITY_COLOR: Record<string, string> = {
  low: "hollow",
  medium: "warning",
  high: "danger",
  critical: "danger",
};

export function ReportView({
  runId,
  agentId,
}: {
  runId: string | null;
  agentId: string | null;
}) {
  const [report, setReport] = useState<BattleReport | null>(null);
  const [candidate, setCandidate] = useState<EvolveResult | null>(null);
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmTrainOnly, setConfirmTrainOnly] = useState(false);

  if (!runId) {
    return (
      <EuiPanel>
        <EuiCallOut title="Run a match first" color="primary" iconType="iInCircle">
          The coach reviews your most recent match. Go to the Match tab and run one.
        </EuiCallOut>
      </EuiPanel>
    );
  }

  const loadReport = async () => {
    setError(null);
    setDecision(null);
    setCandidate(null);
    try {
      setReport(await coachApi.report(runId));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const evolve = async () => {
    setError(null);
    try {
      setCandidate(await coachApi.evolve(runId, agentId || "user_strategy_v0"));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const decide = async (verdict: "accepted" | "rejected") => {
    if (!candidate || !agentId) return;
    if (
      verdict === "accepted" &&
      candidate.generalization_verdict === "train_only" &&
      !confirmTrainOnly
    ) {
      setConfirmTrainOnly(true);
      return;
    }
    const allowTrainOnly =
      candidate.generalization_verdict === "train_only" && verdict === "accepted";
    setConfirmTrainOnly(false);
    setError(null);
    try {
      setDecision(
        await coachApi.decide(
          agentId,
          candidate.candidate_path,
          verdict,
          allowTrainOnly,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <EuiPanel>
      <EuiFlexGroup alignItems="center">
        <EuiFlexItem>
          <EuiText>
            <h2>Coach battle report</h2>
            <p>Run: {runId}</p>
          </EuiText>
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiButton onClick={loadReport}>Load report</EuiButton>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer />
      {error && <EuiCallOut title={error} color="danger" iconType="alert" />}
      {report && (
        <>
          <EuiFlexGroup>
            <EuiFlexItem>
              <EuiStat title={report.outcome} description="Outcome" />
            </EuiFlexItem>
            <EuiFlexItem>
              <EuiStat title={`${report.score}`} description="Policy score" />
            </EuiFlexItem>
            <EuiFlexItem>
              <EuiStat
                title={report.safety.passed ? "pass" : "FAIL"}
                description="Safety"
                titleColor={report.safety.passed ? "success" : "danger"}
              />
            </EuiFlexItem>
          </EuiFlexGroup>
          <EuiSpacer />
          <EuiText>
            <p>{report.summary}</p>
            <h3>Opponent read</h3>
            <p>
              {report.opponent_read.archetype_guess || "unknown"} (
              {report.opponent_read.confidence}) —{" "}
              {report.opponent_read.observed_tactics.join(", ") || "no tactics noted"}
            </p>
          </EuiText>
          {!report.safety.passed && (
            <>
              <EuiSpacer size="s" />
              <EuiCallOut title="Safety failure" color="danger" iconType="alert">
                {report.safety.violations.join("; ")}
              </EuiCallOut>
            </>
          )}
          <EuiSpacer />
          <EuiText>
            <h3>Weaknesses</h3>
          </EuiText>
          <EuiBasicTable
            items={report.weaknesses.map((w, i) => ({ ...w, key: i }))}
            columns={[
              {
                field: "severity",
                name: "Severity",
                width: "110px",
                render: (s: string) => (
                  <EuiBadge color={SEVERITY_COLOR[s] || "hollow"}>{s}</EuiBadge>
                ),
              },
              { field: "phase", name: "Phase", width: "120px" },
              { field: "summary", name: "Finding" },
            ]}
          />
          <EuiSpacer />
          <EuiText>
            <h3>Decision points</h3>
          </EuiText>
          <EuiBasicTable
            items={report.decision_points.map((p, i) => ({ ...p, key: i }))}
            columns={[
              { field: "turn", name: "Turn", width: "70px" },
              { field: "phase", name: "Phase", width: "120px" },
              { field: "situation", name: "Situation" },
              { field: "counterfactual", name: "Could have" },
            ]}
          />
          <EuiHorizontalRule />
          <EuiButton fill onClick={evolve} isDisabled={!agentId}>
            Generate improved strategy
          </EuiButton>
          {!agentId && (
            <EuiText size="s" color="subdued">
              <p>Select an agent in the Match tab to enable evolution.</p>
            </EuiText>
          )}
        </>
      )}
      {candidate && (
        <>
          <EuiSpacer />
          <EuiText>
            <h3>Proposed strategy candidate</h3>
            <p>
              Candidate {candidate.candidate_id}
              {candidate.generalization_verdict && (
                <>
                  {" "}
                  <EuiBadge
                    color={
                      candidate.generalization_verdict === "improved"
                        ? "success"
                        : candidate.generalization_verdict === "train_only"
                          ? "warning"
                          : "danger"
                    }
                  >
                    {candidate.generalization_verdict}
                  </EuiBadge>
                </>
              )}
            </p>
          </EuiText>
          <EuiCodeBlock language="text" paddingSize="m" isCopyable>
            {candidate.strategy_prompt}
          </EuiCodeBlock>
          <EuiSpacer />
          <EuiFlexGroup gutterSize="s">
            <EuiFlexItem grow={false}>
              <EuiButton fill color="primary" onClick={() => decide("accepted")}>
                Accept
              </EuiButton>
            </EuiFlexItem>
            <EuiFlexItem grow={false}>
              <EuiButton color="text" onClick={() => decide("rejected")}>
                Reject
              </EuiButton>
            </EuiFlexItem>
          </EuiFlexGroup>
        </>
      )}
      {decision && (
        <>
          <EuiSpacer />
          <EuiCallOut
            title={
              decision.decision === "accepted"
                ? `Accepted — strategy v${decision.strategy_version}`
                : "Rejected"
            }
            color={decision.decision === "accepted" ? "success" : "primary"}
            iconType={decision.decision === "accepted" ? "check" : "cross"}
          />
        </>
      )}
      {confirmTrainOnly && (
        <EuiConfirmModal
          title="Candidate failed held-out validation"
          onCancel={() => setConfirmTrainOnly(false)}
          onConfirm={() => decide("accepted")}
          cancelButtonText="Keep current strategy"
          confirmButtonText="Apply anyway"
          buttonColor="warning"
        >
          This candidate improved only against the profile it trained on
          (train_only). Applying it risks overfitting. Apply anyway?
        </EuiConfirmModal>
      )}
    </EuiPanel>
  );
}
