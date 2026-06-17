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

export interface BattleReport {
  schema_version: string;
  run_id: string;
  user_role: string;
  outcome: string;
  deal_price: number | null;
  score: number;
  summary: string;
  opponent_read: {
    observed_tactics: string[];
    archetype_guess: string | null;
    confidence: string;
  };
  decision_points: {
    turn: number;
    phase: string;
    situation: string;
    action_taken: string;
    assessment: string;
    counterfactual: string;
  }[];
  weaknesses: {
    id: string;
    phase: string;
    severity: string;
    summary: string;
    evidence_turns: number[];
  }[];
  lessons: { id: string; recommendation: string; suggested_strategy_patch: string | null }[];
  safety: { passed: boolean; violations: string[] };
}

export interface EvolveResult {
  candidate_path: string;
  candidate_id: string;
  strategy_prompt: string;
  applied_lesson_ids: string[];
  generalization_verdict: string | null;
}

export interface DecisionResult {
  agent_id: string;
  decision: string;
  candidate_id?: string;
  strategy_version?: number;
  strategy_prompt?: string;
  lineage?: string;
}

export const coachApi = {
  report: (runId: string) =>
    request<BattleReport>(`/api/runs/${runId}/report`),
  evolve: (runId: string, parentStrategyId: string) =>
    request<EvolveResult>(`/api/runs/${runId}/evolve`, {
      method: "POST",
      body: JSON.stringify({ parent_strategy_id: parentStrategyId }),
    }),
  decide: (
    agentId: string,
    candidatePath: string,
    decision: string,
    allowTrainOnly = false,
  ) =>
    request<DecisionResult>(`/api/agents/${agentId}/strategy`, {
      method: "POST",
      body: JSON.stringify({
        candidate_path: candidatePath,
        decision,
        allow_train_only: allowTrainOnly,
      }),
    }),
};

export interface RatingEntry {
  rank: number;
  participant_id: string;
  rating: number;
  uncertainty: number;
  match_count: number;
}

export interface RatingLeaderboard {
  schema_version: string;
  match_count: number;
  buyer_track: RatingEntry[];
  seller_track: RatingEntry[];
}

export const ratingsApi = {
  get: () => request<RatingLeaderboard>("/api/ratings"),
};

export interface AggregatedWeakness {
  phase: string;
  category: string;
  frequency: number;
  severity_weight: number;
  mean_policy_score: number;
  priority: number;
  opponents: string[];
}

export interface CandidateSlateEntry {
  rank: number;
  phase: string;
  category: string;
  candidate_id: string;
  candidate_path: string;
  strategy_config_path: string;
  verdict: string;
  train_score_delta: number;
  heldout_score_delta: number;
  rerun_mean_score: number;
  generalizes: boolean;
}

export interface TrainingSeason {
  schema_version: string;
  user_role: string;
  baseline_mean_score: number;
  weakness_profile: { matches_analyzed: number; weaknesses: AggregatedWeakness[] };
  slate: CandidateSlateEntry[];
  recommended_candidate_id: string | null;
  recommended_heldout_delta: number;
  trajectory: { baseline_mean_score: number; best_mean_score: number; delta: number };
}

export const seasonApi = {
  run: (agentId: string, k = 3) =>
    request<TrainingSeason>("/api/train-season", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, k }),
    }),
};

export interface GenomeScore {
  genome_id: string;
  fitness: number;
  genes: Record<string, number>;
  parent_ids: string[];
}

export interface GenerationRecord {
  generation: number;
  buyer_best_fitness: number;
  buyer_mean_fitness: number;
  seller_best_fitness: number;
  seller_mean_fitness: number;
  buyer_leaderboard: GenomeScore[];
  seller_leaderboard: GenomeScore[];
}

export interface Coevolution {
  schema_version: string;
  seed: number;
  generations: number;
  population_size: number;
  scenario_count: number;
  evolve_roles: string[];
  generation_records: GenerationRecord[];
  buyer_champion: GenomeScore;
  seller_champion: GenomeScore;
  buyer_champion_lineage: { genome_id: string; parent_ids: string[] }[];
  seller_champion_lineage: { genome_id: string; parent_ids: string[] }[];
  trajectory: { buyer_best_by_generation: number[]; seller_best_by_generation: number[] };
}

export const coevolveApi = {
  run: (payload: Record<string, unknown> = {}) =>
    request<Coevolution>("/api/coevolve", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
