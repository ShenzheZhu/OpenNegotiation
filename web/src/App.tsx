import { useState } from "react";
import {
  EuiPageTemplate,
  EuiHeader,
  EuiHeaderSectionItem,
  EuiTitle,
  EuiTabs,
  EuiTab,
  EuiSpacer,
} from "@elastic/eui";
import { AgentView } from "./views/AgentView";
import { MatchView } from "./views/MatchView";
import { ReportView } from "./views/ReportView";

type TabId = "agent" | "match" | "coach";

const TABS: { id: TabId; label: string }[] = [
  { id: "agent", label: "Agent" },
  { id: "match", label: "Match" },
  { id: "coach", label: "Coach" },
];

export function App() {
  const [tab, setTab] = useState<TabId>("agent");
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [lastAgentId, setLastAgentId] = useState<string | null>(null);

  const onMatch = (runId: string, agentId: string) => {
    setLastRunId(runId);
    setLastAgentId(agentId);
    setTab("coach");
  };

  return (
    <>
      <EuiHeader>
        <EuiHeaderSectionItem>
          <EuiTitle size="s">
            <h1 style={{ padding: "0 12px" }}>OpenNegotiation</h1>
          </EuiTitle>
        </EuiHeaderSectionItem>
      </EuiHeader>
      <EuiPageTemplate restrictWidth={1100} panelled>
        <EuiPageTemplate.Section>
          <EuiTabs>
            {TABS.map((t) => (
              <EuiTab
                key={t.id}
                isSelected={t.id === tab}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </EuiTab>
            ))}
          </EuiTabs>
          <EuiSpacer />
          {tab === "agent" && <AgentView />}
          {tab === "match" && <MatchView onMatch={onMatch} />}
          {tab === "coach" && (
            <ReportView runId={lastRunId} agentId={lastAgentId} />
          )}
        </EuiPageTemplate.Section>
      </EuiPageTemplate>
    </>
  );
}
