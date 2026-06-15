import { useEffect, useState } from "react";
import {
  EuiPanel,
  EuiText,
  EuiSpacer,
  EuiSelect,
  EuiButton,
  EuiCallOut,
  EuiBasicTable,
  EuiBadge,
  EuiFlexGroup,
  EuiFlexItem,
  EuiStat,
} from "@elastic/eui";
import {
  api,
  type AgentSummary,
  type ProfileCard,
  type MatchResult,
  type TraceEvent,
} from "../api/client";

export function MatchView() {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [profiles, setProfiles] = useState<ProfileCard[]>([]);
  const [agentId, setAgentId] = useState("");
  const [opponent, setOpponent] = useState("");
  const [result, setResult] = useState<MatchResult | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.listAgents().then((a) => {
      setAgents(a);
      if (a[0]) setAgentId(a[0].id);
    });
    api.profiles().then((p) => {
      setProfiles(p);
      if (p[0]) setOpponent(p[0].id);
    });
  }, []);

  const run = async () => {
    setError(null);
    setRunning(true);
    setResult(null);
    setEvents([]);
    try {
      const match = await api.runMatch(agentId, opponent);
      setResult(match);
      setEvents(await api.trace(match.run_id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const opponentOptions = profiles.map((p) => ({
    value: p.id,
    text: `${p.name} (${p.difficulty})`,
  }));

  return (
    <EuiPanel>
      <EuiText>
        <h2>Run a match</h2>
      </EuiText>
      <EuiSpacer />
      <EuiFlexGroup>
        <EuiFlexItem>
          <EuiSelect
            prepend="Agent"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            options={agents.map((a) => ({ value: a.id, text: a.id }))}
          />
        </EuiFlexItem>
        <EuiFlexItem>
          <EuiSelect
            prepend="Opponent"
            value={opponent}
            onChange={(e) => setOpponent(e.target.value)}
            options={opponentOptions}
          />
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiButton fill onClick={run} isLoading={running} isDisabled={!agentId}>
            Run
          </EuiButton>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer />
      {error && <EuiCallOut title={error} color="danger" iconType="alert" />}
      {result && (
        <>
          <EuiFlexGroup>
            <EuiFlexItem>
              <EuiStat title={result.outcome} description="Outcome" />
            </EuiFlexItem>
            <EuiFlexItem>
              <EuiStat
                title={result.deal_price != null ? `$${result.deal_price}` : "—"}
                description="Deal price"
              />
            </EuiFlexItem>
            <EuiFlexItem>
              <EuiStat
                title={result.policy_score != null ? `${result.policy_score}` : "—"}
                description="Policy score"
              />
            </EuiFlexItem>
          </EuiFlexGroup>
          <EuiSpacer />
          <EuiText>
            <h3>Trace replay</h3>
          </EuiText>
          <EuiBasicTable
            items={events.map((e, i) => ({ ...e, key: i }))}
            columns={[
              { field: "turn", name: "Turn", width: "70px" },
              { field: "role", name: "Role", width: "90px" },
              {
                field: "action_type",
                name: "Action",
                render: (a: string) => <EuiBadge>{a}</EuiBadge>,
              },
              {
                name: "Detail",
                render: (e: TraceEvent) =>
                  e.offer ? `offer $${e.offer.price}` : e.content || "—",
              },
              {
                field: "private",
                name: "Visibility",
                width: "100px",
                render: (p: boolean) => (p ? "private" : "public"),
              },
            ]}
          />
        </>
      )}
    </EuiPanel>
  );
}
