export interface ProfileCard {
  id: string;
  name: string;
  role: string;
  archetype: string;
  difficulty: string;
  summary: string;
  tags: string[];
}

export interface AgentSummary {
  id: string;
  role: string;
  model?: string | null;
  endpoint?: string | null;
  strategy_prompt: string;
  has_key: boolean;
}

export interface TraceEvent {
  turn: number;
  role: string;
  actor: string;
  action_type: string;
  content: string;
  offer?: { price: number; note: string } | null;
  private: boolean;
}

export interface MatchResult {
  run_id: string;
  agent_id: string;
  opponent_profile_id: string;
  outcome: string;
  deal_price: number | null;
  policy_score: number | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || `request failed: ${response.status}`);
  }
  return data as T;
}

export const api = {
  profiles: () =>
    request<{ profiles: ProfileCard[] }>("/api/profiles").then((d) => d.profiles),
  listAgents: () =>
    request<{ agents: AgentSummary[] }>("/api/agents").then((d) => d.agents),
  defineAgent: (payload: Record<string, unknown>) =>
    request<AgentSummary>("/api/agents", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  runMatch: (agentId: string, opponentProfileId: string) =>
    request<MatchResult>("/api/matches", {
      method: "POST",
      body: JSON.stringify({
        agent_id: agentId,
        opponent_profile_id: opponentProfileId,
      }),
    }),
  trace: (runId: string) =>
    request<{ events: TraceEvent[] }>(`/api/runs/${runId}/trace`).then(
      (d) => d.events,
    ),
};
