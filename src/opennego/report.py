"""Static HTML report generation for small OpenNegotiation demos."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from opennego.artifacts import (
    ArtifactValidationError,
    MetricReport,
    RunManifest,
    ScenarioArtifact,
    TraceEventRecord,
    load_manifest,
    load_metric_report,
    load_scenario_artifact,
    load_trace,
)
from opennego.branding import PRODUCT_NAME
from opennego.leaderboard import LEADERBOARD_SCHEMA_VERSION
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH, StrategyProfile, load_strategy_registry


@dataclass(frozen=True)
class DemoRun:
    output_dir: Path
    manifest: RunManifest
    scenario: ScenarioArtifact
    metrics: MetricReport
    trace: Sequence[TraceEventRecord]


@dataclass(frozen=True)
class ModelAttempt:
    model: str
    status: str
    output_dir: str
    outcome: str | None = None
    deal_price: float | None = None
    completed_turns: int | None = None
    llm_call_count: int = 0
    total_tokens: int | None = None
    cost_usd: float | None = None
    error_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BattleLessonView:
    id: str
    severity: str
    category: str
    finding: str
    recommendation: str
    suggested_strategy_patch: str | None = None
    evidence: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class BattleReportView:
    run_id: str
    user_role: str
    opponent_profile_id: str | None
    outcome: str
    deal_price: float | None
    score: float
    summary: str
    failure_modes: tuple[str, ...]
    strengths: tuple[str, ...]
    lessons: tuple[BattleLessonView, ...]
    suggested_strategy_prompt: str


@dataclass(frozen=True)
class StrategyCandidateView:
    candidate_id: str
    parent_strategy_id: str
    iteration: int
    applied_lesson_ids: tuple[str, ...]
    rerun_command: str


@dataclass(frozen=True)
class LeaderboardRunView:
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
class ParticipantCoverageView:
    rank: int
    participant_id: str
    roles: tuple[str, ...]
    role_coverage: float
    unique_run_count: int
    average_score: float
    coverage_adjusted_score: float
    balanced_average_score: float | None


@dataclass(frozen=True)
class LeaderboardSummaryView:
    schema_version: str
    run_count: int
    participant_summaries: tuple[ParticipantCoverageView, ...]
    runs: tuple[LeaderboardRunView, ...]


def write_demo_report(input_dir: str | Path, output_file: str | Path) -> Path:
    """Write a static HTML dashboard for a small benchmark artifact directory."""

    runs = load_demo_runs(input_dir)
    if not runs:
        raise ValueError(f"{input_dir}: no benchmark run artifacts found")
    attempts = load_model_attempts(input_dir)
    battle_reports = load_battle_reports(input_dir)
    strategy_candidates = load_strategy_candidates(input_dir)
    strategy_profiles = load_strategy_profiles()
    leaderboard_summary = load_leaderboard_summary(input_dir)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = render_demo_report(
        runs,
        attempts=attempts,
        battle_reports=battle_reports,
        strategy_candidates=strategy_candidates,
        strategy_profiles=strategy_profiles,
        leaderboard_summary=leaderboard_summary,
    )
    output_path.write_text(
        _strip_trailing_whitespace(html_text),
        encoding="utf-8",
    )
    return output_path


def _strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def load_demo_runs(input_dir: str | Path) -> tuple[DemoRun, ...]:
    base = Path(input_dir)
    candidates = [base] if (base / "metrics.json").exists() else sorted(base.iterdir())
    runs: list[DemoRun] = []
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        try:
            runs.append(
                DemoRun(
                    output_dir=candidate,
                    manifest=load_manifest(candidate / "manifest.json"),
                    scenario=load_scenario_artifact(candidate / "scenario.json"),
                    metrics=load_metric_report(candidate / "metrics.json"),
                    trace=load_trace(candidate / "trace.jsonl"),
                )
            )
        except (OSError, ArtifactValidationError, ValueError):
            continue
    return tuple(sorted(runs, key=lambda run: run.manifest.run_id))


def load_model_attempts(input_dir: str | Path) -> tuple[ModelAttempt, ...]:
    summary_path = Path(input_dir) / "summary.json"
    if not summary_path.exists():
        return ()
    try:
        data = json.loads(summary_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ()
    runs = data.get("runs") if isinstance(data, Mapping) else None
    if not isinstance(runs, list):
        return ()
    attempts = []
    for item in runs:
        if isinstance(item, Mapping):
            attempts.append(_attempt_from_mapping(item))
    return tuple(attempts)


def load_battle_reports(input_dir: str | Path) -> tuple[BattleReportView, ...]:
    base = Path(input_dir)
    candidate_paths = sorted(base.glob("battle_report*.json"))
    reports = []
    for path in candidate_paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, Mapping) and data.get("schema_version") == "opennego.policy_learning.v1":
            reports.append(_battle_report_from_mapping(data))
    return tuple(reports)


def load_strategy_candidates(input_dir: str | Path) -> tuple[StrategyCandidateView, ...]:
    base = Path(input_dir)
    candidate_paths = sorted(base.glob("strategy_candidate*.json"))
    candidates = []
    for path in candidate_paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(data, Mapping)
            and data.get("schema_version") == "opennego.strategy_evolution.v1"
        ):
            candidates.append(_strategy_candidate_from_mapping(data))
    return tuple(candidates)


def load_strategy_profiles(
    registry_path: str | Path = DEFAULT_NPC_REGISTRY_PATH,
) -> tuple[StrategyProfile, ...]:
    try:
        return load_strategy_registry(registry_path).profiles
    except (OSError, ValueError):
        return ()


def load_leaderboard_summary(input_dir: str | Path) -> LeaderboardSummaryView | None:
    path = Path(input_dir) / "leaderboard_summary.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, Mapping) or data.get("schema_version") != LEADERBOARD_SCHEMA_VERSION:
        return None
    raw_runs = data.get("runs")
    raw_participants = data.get("participant_summaries")
    if not isinstance(raw_runs, list) or not isinstance(raw_participants, list):
        return None
    runs = tuple(
        _leaderboard_run_from_mapping(item)
        for item in raw_runs
        if isinstance(item, Mapping)
    )
    participants = tuple(
        _participant_coverage_from_mapping(item)
        for item in raw_participants
        if isinstance(item, Mapping)
    )
    if not runs:
        return None
    return LeaderboardSummaryView(
        schema_version=LEADERBOARD_SCHEMA_VERSION,
        run_count=_int_value(data.get("run_count"), len(runs)),
        participant_summaries=participants,
        runs=runs,
    )


def render_demo_report(
    runs: Sequence[DemoRun],
    *,
    attempts: Sequence[ModelAttempt] = (),
    battle_reports: Sequence[BattleReportView] = (),
    strategy_candidates: Sequence[StrategyCandidateView] = (),
    strategy_profiles: Sequence[StrategyProfile] = (),
    leaderboard_summary: LeaderboardSummaryView | None = None,
) -> str:
    primary = runs[0]
    leaderboard = sorted(runs, key=_demo_score, reverse=True)
    product = primary.scenario.product
    market_reference = product.market_reference
    reference_price = (
        _money(market_reference.reference_price, market_reference.currency)
        if market_reference
        else "not set"
    )
    sample_size = (
        str(market_reference.sample_size)
        if market_reference and market_reference.sample_size is not None
        else "fixture"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{PRODUCT_NAME} Demo Dashboard</title>
  <style>
    :root {{
      --ink: #111827;
      --muted: #5f6b7a;
      --line: #dde5ee;
      --panel: #ffffff;
      --soft: #f7fafc;
      --soft-2: #edf6f7;
      --accent: #087f8c;
      --accent-dark: #075f68;
      --accent-2: #b45309;
      --accent-3: #2563eb;
      --danger: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #f8fafc;
      font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(255, 255, 255, .92);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }}
    .nav {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 14px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    .brand {{ font-weight: 800; letter-spacing: 0; }}
    .navlinks {{ display: flex; gap: 18px; color: var(--muted); font-size: 14px; flex-wrap: wrap; }}
    .shell {{ max-width: 1120px; margin: 0 auto; padding: 34px 22px 54px; }}
    .hero {{
      text-align: center;
      padding: 46px 18px 30px;
    }}
    h1 {{ margin: 12px auto 12px; max-width: 920px; font-size: 52px; line-height: 1.06; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 26px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; letter-spacing: 0; }}
    p {{ margin: 0; }}
    .eyebrow {{ color: var(--accent-dark); font-size: 13px; font-weight: 700; text-transform: uppercase; }}
    .subtitle {{ max-width: 820px; margin: 0 auto; color: var(--muted); font-size: 18px; }}
    .actions {{ margin-top: 22px; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }}
    .button {{
      display: inline-block;
      padding: 9px 14px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 999px;
      font-weight: 650;
    }}
    .button.primary {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .kpis {{ margin: 30px auto 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; max-width: 880px; }}
    .kpi {{
      padding: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      text-align: left;
      box-shadow: 0 10px 30px rgba(15, 23, 42, .04);
    }}
    .kpi .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .kpi .value {{ margin-top: 4px; font-size: 22px; font-weight: 750; overflow-wrap: anywhere; }}
    .section {{
      margin-top: 24px;
      padding: 26px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 12px 32px rgba(15, 23, 42, .035);
    }}
    .section-head {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin-bottom: 16px; }}
    .section-copy {{ max-width: 720px; color: var(--muted); }}
    .grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .card {{ padding: 16px; background: var(--soft); border: 1px solid var(--line); border-radius: 8px; }}
    .lesson-card {{ padding: 16px; background: #fffaf0; border: 1px solid #f3d7a4; border-radius: 8px; }}
    .profile-card {{ padding: 16px; background: #f8fbff; border: 1px solid var(--line); border-radius: 8px; }}
    .prompt-patch {{ margin-top: 12px; padding: 12px; background: #10212b; color: #e7f6f2; border-radius: 8px; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .severity-high {{ color: #b91c1c; font-weight: 750; }}
    .severity-medium {{ color: #b45309; font-weight: 750; }}
    .severity-low {{ color: var(--accent-dark); font-weight: 750; }}
    .muted {{ color: var(--muted); }}
    .overview-figure {{
      padding: 18px;
      background: linear-gradient(180deg, #ffffff 0%, #eff8f9 100%);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .figure-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .figure-node {{ min-height: 120px; padding: 16px; background: rgba(255, 255, 255, .9); border: 1px solid var(--line); border-radius: 8px; }}
    .figure-node strong {{ display: block; margin-bottom: 7px; }}
    .figure-caption {{ margin-top: 12px; color: var(--muted); font-size: 13px; text-align: center; }}
    .flow {{ display: grid; grid-template-columns: repeat(6, minmax(110px, 1fr)); gap: 10px; }}
    .step {{ padding: 12px; min-height: 90px; background: #f9fbfc; border: 1px solid var(--line); border-radius: 8px; }}
    .step strong {{ display: block; margin-bottom: 5px; }}
    .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0 14px; }}
    .tab {{ padding: 7px 12px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); background: #fff; font-size: 13px; }}
    .tab.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
    table {{ width: 100%; border-collapse: collapse; }}
    .table-scroll {{ width: 100%; overflow-x: auto; }}
    .table-scroll table {{ min-width: 760px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .score {{ font-weight: 800; color: var(--accent); }}
    .pill {{ display: inline-block; padding: 3px 9px; border: 1px solid var(--line); border-radius: 999px; background: #fff; font-size: 12px; }}
    .trace {{ display: grid; gap: 10px; }}
    .event {{ padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #fbfcfd; }}
    .event-head {{ display: flex; gap: 8px; align-items: center; justify-content: space-between; }}
    .role {{ font-weight: 700; }}
    .buyer {{ color: var(--accent-3); }}
    .seller {{ color: var(--accent-2); }}
    .system {{ color: var(--danger); }}
    .private {{ color: var(--muted); font-size: 12px; }}
    .bar-track {{ width: 120px; height: 8px; overflow: hidden; background: #dde6e7; border-radius: 999px; }}
    .bar-fill {{ height: 100%; background: var(--accent); }}
    footer {{ margin-top: 18px; color: var(--muted); font-size: 12px; text-align: center; }}
    @media (max-width: 860px) {{
      .nav {{ align-items: flex-start; flex-direction: column; }}
      .hero, .grid-3, .grid-2, .flow, .figure-grid, .kpis {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 36px; }}
      .section-head {{ align-items: flex-start; flex-direction: column; }}
      .kpi .value {{ font-size: 20px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <nav class="nav">
      <a class="brand" href="#">{PRODUCT_NAME}</a>
      <div class="navlinks">
        <a href="#overview">Overview</a>
        <a href="#mechanism">Mechanism</a>
        <a href="#leaderboard">Leaderboard</a>
        {_attempt_nav_link(attempts)}
        {_training_nav_link(battle_reports)}
        {_marketplace_nav_link(strategy_profiles)}
        <a href="#trace">Trace</a>
        <a href="#findings">Findings</a>
      </div>
    </nav>
  </header>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">Agentic negotiation benchmark</p>
      <h1>Benchmarking AI agents in real-market negotiation and transaction settings</h1>
      <p class="subtitle">{PRODUCT_NAME} evaluates how buyer and seller agents search market evidence, bargain under asymmetric tools, and settle realistic consumer-to-consumer deals.</p>
      <div class="actions">
        <a class="button primary" href="#leaderboard">View leaderboard preview</a>
        <a class="button" href="#overview">Explore mechanism</a>
        {_training_button(battle_reports)}
        <a class="button" href="../../docs/real_market_benchmark_design.md">Design notes</a>
      </div>
      <div class="kpis">
        <div class="kpi"><div class="label">Demo Runs</div><div class="value">{len(attempts) if attempts else len(runs)}</div></div>
        <div class="kpi"><div class="label">Product Cluster</div><div class="value">{_escape(_humanize(product.condition))}</div></div>
        <div class="kpi"><div class="label">Market Reference</div><div class="value">{reference_price}</div></div>
        <div class="kpi"><div class="label">Training Reports</div><div class="value">{len(battle_reports)}</div></div>
      </div>
    </section>

    <section id="overview" class="section">
      <div class="section-head">
        <div>
          <h2>{PRODUCT_NAME} Overview</h2>
          <p class="section-copy">A market lifecycle view of negotiation: agents do not just chat, they gather evidence, make structured offers, and pass accepted deals through transaction validation.</p>
        </div>
        <span class="pill">Artifact-backed demo</span>
      </div>
      <div class="overview-figure">
        <div class="figure-grid">
          <div class="figure-node"><strong>Buyer Agent</strong><span class="muted">Budget, preferences, search tools, and offer policy.</span></div>
          <div class="figure-node"><strong>Market Evidence</strong><span class="muted">Sold comps, provenance, noisy/stale/failure regimes.</span></div>
          <div class="figure-node"><strong>Policy Learning</strong><span class="muted">Battle reports extract trace-grounded lessons and strategy prompt patches.</span></div>
          <div class="figure-node"><strong>Strategy Marketplace</strong><span class="muted">Preset NPC profiles expose anchors, stale evidence, hidden fees, and probing tactics.</span></div>
        </div>
        <p class="figure-caption">The demo loop is benchmark, diagnose, patch strategy, and spar against harder NPC profiles.</p>
      </div>
    </section>

    <section class="section">
      <h2>Why Choose {PRODUCT_NAME}</h2>
      <div class="grid-3">
        <div class="card"><h3>Agentic, not prompt-only</h3><p class="muted">Agents can use tools for market search, provenance checks, and transaction reasoning before making offers.</p></div>
        <div class="card"><h3>Training-ready</h3><p class="muted">Every run can become a battle report with failure diagnoses and strategy-layer prompt patches.</p></div>
        <div class="card"><h3>Marketplace-driven</h3><p class="muted">Curated NPC strategies give users repeatable sparring partners for systematic optimization.</p></div>
      </div>
    </section>

    <section id="mechanism" class="section">
      <h2>Mechanism</h2>
      <div class="flow">
        <div class="step"><strong>1. Scenario</strong><span class="muted">Product cluster, condition, budget, private reservation, market reference.</span></div>
        <div class="step"><strong>2. Tools</strong><span class="muted">Private or shared market-comparable search with provenance.</span></div>
        <div class="step"><strong>3. Negotiation</strong><span class="muted">Structured messages, offers, accepts, rejects, and tool calls.</span></div>
        <div class="step"><strong>4. Settlement</strong><span class="muted">Shipping, tax, fees, escrow, payment, and risk outcomes.</span></div>
        <div class="step"><strong>5. Metrics</strong><span class="muted">Deal rate, market gap, utility, violations, and tool behavior.</span></div>
        <div class="step"><strong>6. Replay</strong><span class="muted">Versioned artifacts support audit, visualization, and leaderboard views.</span></div>
      </div>
    </section>

    <section id="leaderboard" class="section">
      <h2>Leaderboard Preview</h2>
      <p class="section-copy">The full benchmark should use scorecard tracks as the primary ranking surface. Arena/Elo can be a smaller secondary track.</p>
      {_leaderboard_source_pill(leaderboard_summary)}
      <div class="tabs">
        <span class="tab active">Overall</span>
        <span class="tab">Buyer Track</span>
        <span class="tab">Seller Track</span>
        <span class="tab">Tool-Aware</span>
        <span class="tab">Mini Arena</span>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Model / Run</th>
              <th>Regime</th>
              <th>Score</th>
              <th>Deal</th>
              <th>Market Gap</th>
              <th>Tools</th>
              <th>Transaction</th>
            </tr>
          </thead>
          <tbody>
            {_leaderboard_rows_from_summary(leaderboard_summary) if leaderboard_summary else _leaderboard_rows(leaderboard)}
          </tbody>
        </table>
      </div>
      {_participant_coverage_table(leaderboard_summary)}
    </section>

    {_attempt_status_section(attempts)}

    {_policy_learning_section(battle_reports, strategy_candidates)}

    {_strategy_marketplace_section(strategy_profiles)}

    <section id="findings" class="section">
      <h2>Key Findings From This Demo</h2>
      <div class="grid-3">
        <div class="card"><h3>Benchmark is the evidence layer</h3><p class="muted">Scenario, manifest, trace, and metrics artifacts remain the source of truth for scoring and replay.</p></div>
        <div class="card"><h3>Training turns scores into edits</h3><p class="muted">Battle reports cite trace events before recommending strategy prompt patches.</p></div>
        <div class="card"><h3>NPCs define the curriculum</h3><p class="muted">Marketplace profiles expose anchors, stale evidence, hidden fees, reservation probes, and tool overuse.</p></div>
      </div>
    </section>

    <section id="trace" class="section">
      <h2>Trace Replay</h2>
      <p class="muted">Showing the highest-scoring run: {_escape(leaderboard[0].manifest.run_id)}</p>
      <div class="trace">
        {_trace_events(leaderboard[0])}
      </div>
    </section>

    <footer>
      Generated from {PRODUCT_NAME} benchmark and policy-learning artifacts. This is a fixture-backed demo surface, not a live marketplace collection.
    </footer>
  </main>
</body>
</html>
"""


def _attempt_status_section(attempts: Sequence[ModelAttempt]) -> str:
    if not attempts:
        return ""
    return f"""
    <section id="attempts" class="section">
      <h2>Run Attempt Status</h2>
      <p class="section-copy">Live model demos keep every model attempt visible. Completed attempts feed the leaderboard; failed attempts keep a redacted failure artifact for audit.</p>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Status</th>
              <th>Outcome</th>
              <th>LLM Calls</th>
              <th>Total Tokens</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {_attempt_rows(attempts)}
          </tbody>
        </table>
      </div>
    </section>
"""


def _attempt_nav_link(attempts: Sequence[ModelAttempt]) -> str:
    if not attempts:
        return ""
    return '<a href="#attempts">Runs</a>'


def _training_nav_link(reports: Sequence[BattleReportView]) -> str:
    if not reports:
        return ""
    return '<a href="#training">Training</a>'


def _marketplace_nav_link(profiles: Sequence[StrategyProfile]) -> str:
    if not profiles:
        return ""
    return '<a href="#marketplace">Marketplace</a>'


def _training_button(reports: Sequence[BattleReportView]) -> str:
    if not reports:
        return ""
    return '<a class="button" href="#training">Review training advice</a>'


def _policy_learning_section(
    reports: Sequence[BattleReportView],
    candidates: Sequence[StrategyCandidateView],
) -> str:
    if not reports:
        return ""
    report = reports[0]
    candidate = candidates[0] if candidates else None
    return f"""
    <section id="training" class="section">
      <div class="section-head">
        <div>
          <h2>Training / Prompt Optimization</h2>
          <p class="section-copy">Battle reports turn benchmark artifacts into strategy-layer edits. The base protocol remains fixed; only the user's strategy prompt changes.</p>
        </div>
        <span class="pill">Policy score {report.score:.1f}</span>
      </div>
      <div class="grid-2">
        <div class="card">
          <h3>Battle Summary</h3>
          <p class="muted">{_escape(report.summary)}</p>
          <p class="muted">Run: {_escape(report.run_id)}</p>
          <p class="muted">Failure modes: {_escape(', '.join(report.failure_modes) or 'none')}</p>
        </div>
        <div class="card">
          <h3>Strategy Patch</h3>
          <div class="prompt-patch">{_escape(report.suggested_strategy_prompt)}</div>
        </div>
        {_strategy_candidate_card(candidate)}
      </div>
      <div class="grid-2" style="margin-top:14px;">
        {_lesson_cards(report.lessons)}
      </div>
    </section>
"""


def _strategy_candidate_card(candidate: StrategyCandidateView | None) -> str:
    if candidate is None:
        return ""
    applied = ", ".join(candidate.applied_lesson_ids) or "none"
    return (
        '<div class="card">'
        "<h3>Strategy Candidate</h3>"
        f"<p class=\"muted\">{_escape(candidate.candidate_id)}</p>"
        f"<p class=\"muted\">Parent: {_escape(candidate.parent_strategy_id)} "
        f"iteration {candidate.iteration}</p>"
        f"<p class=\"muted\">Applied lessons: {_escape(applied)}</p>"
        f"<div class=\"prompt-patch\">{_escape(candidate.rerun_command)}</div>"
        "</div>"
    )


def _strategy_marketplace_section(profiles: Sequence[StrategyProfile]) -> str:
    if not profiles:
        return ""
    return f"""
    <section id="marketplace" class="section">
      <div class="section-head">
        <div>
          <h2>Strategy Marketplace</h2>
          <p class="section-copy">Preset NPC profiles provide repeatable sparring partners. Each profile separates fixed sandbox base logic from editable strategy behavior.</p>
        </div>
        <span class="pill">{len(profiles)} NPC profiles</span>
      </div>
      <div class="grid-3">
        {_profile_cards(profiles[:6])}
      </div>
    </section>
"""


def _lesson_cards(lessons: Sequence[BattleLessonView]) -> str:
    if not lessons:
        return '<div class="lesson-card"><h3>No deterministic lessons</h3><p class="muted">No high-signal policy issue was detected.</p></div>'
    cards = []
    for lesson in lessons[:4]:
        evidence = "; ".join(_evidence_label(item) for item in lesson.evidence[:2])
        cards.append(
            "<div class=\"lesson-card\">"
            f"<h3>{_escape(lesson.category.replace('_', ' ').title())}</h3>"
            f"<p class=\"muted\">{_escape(lesson.id)}</p>"
            f"<p class=\"severity-{_escape(lesson.severity)}\">{_escape(lesson.severity.upper())}</p>"
            f"<p>{_escape(lesson.finding)}</p>"
            f"<p class=\"muted\">{_escape(lesson.recommendation)}</p>"
            f"<p class=\"muted\">Evidence: {_escape(evidence or 'trace-linked')}</p>"
            "</div>"
        )
    return "\n".join(cards)


def _profile_cards(profiles: Sequence[StrategyProfile]) -> str:
    cards = []
    for profile in profiles:
        traps = "; ".join(profile.expected_traps[:2])
        tags = ", ".join(profile.tags[:4])
        cards.append(
            "<div class=\"profile-card\">"
            f"<h3>{_escape(profile.name)}</h3>"
            f"<p><span class=\"pill\">{_escape(profile.role.value)}</span> <span class=\"pill\">{_escape(profile.difficulty)}</span></p>"
            f"<p class=\"muted\">{_escape(profile.summary)}</p>"
            f"<p class=\"muted\">Tests: {_escape(traps)}</p>"
            f"<p class=\"muted\">Tags: {_escape(tags)}</p>"
            "</div>"
        )
    return "\n".join(cards)


def _attempt_rows(attempts: Sequence[ModelAttempt]) -> str:
    rows = []
    for attempt in attempts:
        rows.append(
            "<tr>"
            f"<td>{_escape(_shorten_model(attempt.model))}</td>"
            f"<td><span class=\"pill\">{_escape(attempt.status)}</span></td>"
            f"<td>{_escape(attempt.outcome or 'n/a')} {_money_or_empty(attempt.deal_price) if attempt.deal_price is not None else ''}</td>"
            f"<td>{attempt.llm_call_count}</td>"
            f"<td>{_escape(attempt.total_tokens if attempt.total_tokens is not None else 'n/a')}</td>"
            f"<td>{_escape(_attempt_error(attempt))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _leaderboard_source_pill(summary: LeaderboardSummaryView | None) -> str:
    if summary is None:
        return '<p class="muted" style="margin:10px 0;">Leaderboard source: run artifacts fallback.</p>'
    return (
        '<p class="muted" style="margin:10px 0;">'
        f"Leaderboard artifact {_escape(summary.schema_version)} "
        f"with {summary.run_count} scored runs."
        "</p>"
    )


def _leaderboard_rows_from_summary(summary: LeaderboardSummaryView | None) -> str:
    if summary is None:
        return ""
    rows = []
    for row in summary.runs:
        metrics = row.metrics
        gap = metrics.get("normalized_market_gap", 0.0)
        gap_width = max(0, min(100, 100 - gap * 50))
        rows.append(
            "<tr>"
            f"<td>{row.rank}</td>"
            f"<td>{_participant_matchup_label(row)}</td>"
            f"<td>{_escape(row.tool_regime_id)}</td>"
            f"<td><span class=\"score\">{row.score:.1f}</span></td>"
            f"<td>{_escape(row.outcome)} at {_money_or_empty(row.deal_price)}</td>"
            f"<td>{gap:.2f}<div class=\"bar-track\"><div class=\"bar-fill\" style=\"width:{gap_width:.0f}%\"></div></div></td>"
            f"<td>{metrics.get('tool_call_count', 0.0):.0f} calls, {metrics.get('tool_failure_count', 0.0):.0f} failures</td>"
            f"<td>{metrics.get('transaction_completed_rate', 0.0):.0f}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _participant_coverage_table(summary: LeaderboardSummaryView | None) -> str:
    if summary is None or not summary.participant_summaries:
        return ""
    return f"""
      <h3 style="margin-top:22px;">Participant Coverage</h3>
      <p class="section-copy">Coverage shows whether the same model or agent has been evaluated as buyer, seller, or both before comparing balanced performance.</p>
      <div class="table-scroll" style="margin-top:10px;">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Participant</th>
              <th>Roles</th>
              <th>Coverage</th>
              <th>Avg Score</th>
              <th>Coverage Adj.</th>
              <th>Balanced</th>
              <th>Runs</th>
            </tr>
          </thead>
          <tbody>
            {_participant_coverage_rows(summary.participant_summaries)}
          </tbody>
        </table>
      </div>
"""


def _participant_coverage_rows(participants: Sequence[ParticipantCoverageView]) -> str:
    rows = []
    for participant in participants:
        rows.append(
            "<tr>"
            f"<td>{participant.rank}</td>"
            f"<td>{_escape(_shorten_model(participant.participant_id))}</td>"
            f"<td>{_escape(', '.join(participant.roles))}</td>"
            f"<td>{participant.role_coverage:.2f}</td>"
            f"<td><span class=\"score\">{participant.average_score:.1f}</span></td>"
            f"<td>{participant.coverage_adjusted_score:.1f}</td>"
            f"<td>{_score_or_empty(participant.balanced_average_score)}</td>"
            f"<td>{participant.unique_run_count}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _participant_matchup_label(row: LeaderboardRunView) -> str:
    buyer = _escape(_shorten_model(row.buyer_participant_id))
    seller = _escape(_shorten_model(row.seller_participant_id))
    run_id = _escape(_truncate(row.run_id, 72))
    return (
        f"<strong>{buyer}</strong>"
        f"<div class=\"muted\">vs {seller}</div>"
        f"<div class=\"muted\">{run_id}</div>"
    )


def _leaderboard_rows(runs: Sequence[DemoRun]) -> str:
    rows = []
    for index, run in enumerate(runs, start=1):
        metrics = run.metrics.metrics
        score = _demo_score(run)
        gap = metrics.get("normalized_market_gap", 0.0)
        gap_width = max(0, min(100, 100 - gap * 50))
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{_escape(_run_label(run))}</td>"
            f"<td>{_escape(_tool_regime_id(run))}</td>"
            f"<td><span class=\"score\">{score:.1f}</span></td>"
            f"<td>{_escape(run.metrics.outcome)} at {_money_or_empty(run.metrics.deal_price)}</td>"
            f"<td>{metrics.get('normalized_market_gap', 0.0):.2f}<div class=\"bar-track\"><div class=\"bar-fill\" style=\"width:{gap_width:.0f}%\"></div></div></td>"
            f"<td>{metrics.get('tool_call_count', 0.0):.0f} calls, {metrics.get('tool_failure_count', 0.0):.0f} failures</td>"
            f"<td>{metrics.get('transaction_completed_rate', 0.0):.0f}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _trace_events(run: DemoRun) -> str:
    if not run.trace:
        return "<div class=\"event muted\">No trace events recorded.</div>"
    return "\n".join(_trace_event(event) for event in run.trace)


def _trace_event(event: TraceEventRecord) -> str:
    role = event.role.value
    details = []
    if event.offer is not None:
        details.append(f"offer {_money(event.offer.price)}")
    if event.tool_call is not None:
        details.append(f"tool {event.tool_call.name}")
    if event.tool_result is not None:
        median = event.tool_result.get("median_price")
        count = event.tool_result.get("count")
        if median is not None:
            details.append(f"median {_money(float(median))}")
        if count is not None:
            details.append(f"{count} comps")
    if event.transaction is not None:
        details.append(f"transaction {event.transaction.status}")
    if event.content:
        details.append(event.content)
    detail_text = " | ".join(_escape(str(item)) for item in details) or "&nbsp;"
    privacy = "private" if event.private else "public"
    return (
        "<div class=\"event\">"
        "<div class=\"event-head\">"
        f"<span><span class=\"role {role}\">{_escape(role)}</span> | {_escape(event.action_type.value)} | turn {event.turn}</span>"
        f"<span class=\"private\">{privacy}</span>"
        "</div>"
        f"<div class=\"muted\">{detail_text}</div>"
        "</div>"
    )


def _demo_score(run: DemoRun) -> float:
    metrics = run.metrics.metrics
    deal = metrics.get("deal_rate", 0.0)
    tx = metrics.get("transaction_completed_rate", 0.0)
    gap = metrics.get("normalized_market_gap", 0.0)
    gap_component = max(0.0, 1.0 - min(gap, 2.0) / 2.0)
    tool_calls = metrics.get("tool_call_count", 0.0)
    failures = metrics.get("tool_failure_count", 0.0)
    tool_quality = 1.0 if tool_calls == 0 else max(0.0, 1.0 - failures / tool_calls)
    return round(100 * (0.35 * deal + 0.25 * tx + 0.25 * gap_component + 0.15 * tool_quality), 1)


def _tool_regime_id(run: DemoRun) -> str:
    regime = run.manifest.tool_regime
    value = regime.get("id") if isinstance(regime, dict) else None
    return str(value or "unknown")


def _run_label(run: DemoRun) -> str:
    models = run.manifest.models
    if isinstance(models, dict) and models.get("buyer"):
        return _shorten_model(str(models["buyer"]))
    return run.metrics.scenario_id


def _shorten_model(model: str) -> str:
    return model.removeprefix("openrouter/")


def _attempt_from_mapping(data: Mapping[str, Any]) -> ModelAttempt:
    return ModelAttempt(
        model=str(data.get("model", "")),
        status=str(data.get("status", "unknown")),
        output_dir=str(data.get("output_dir", "")),
        outcome=_optional_str(data.get("outcome")),
        deal_price=_optional_float(data.get("deal_price")),
        completed_turns=_optional_int(data.get("completed_turns")),
        llm_call_count=int(data.get("llm_call_count") or 0),
        total_tokens=_optional_int(data.get("total_tokens")),
        cost_usd=_optional_float(data.get("cost_usd")),
        error_type=_optional_str(data.get("error_type")),
        error=_optional_str(data.get("error")),
    )


def _attempt_error(attempt: ModelAttempt) -> str:
    if attempt.status == "completed":
        return "n/a"
    prefix = f"{attempt.error_type}: " if attempt.error_type else ""
    return _truncate(prefix + (attempt.error or "unknown failure"), 120)


def _battle_report_from_mapping(data: Mapping[str, Any]) -> BattleReportView:
    lessons = data.get("lessons", ())
    return BattleReportView(
        run_id=str(data.get("run_id", "")),
        user_role=str(data.get("user_role", "")),
        opponent_profile_id=_optional_str(data.get("opponent_profile_id")),
        outcome=str(data.get("outcome", "")),
        deal_price=_optional_float(data.get("deal_price")),
        score=float(data.get("score", 0.0)),
        summary=str(data.get("summary", "")),
        failure_modes=tuple(str(item) for item in data.get("failure_modes", ())),
        strengths=tuple(str(item) for item in data.get("strengths", ())),
        lessons=tuple(
            _lesson_from_mapping(item)
            for item in lessons
            if isinstance(item, Mapping)
        ),
        suggested_strategy_prompt=str(data.get("suggested_strategy_prompt", "")),
    )


def _strategy_candidate_from_mapping(data: Mapping[str, Any]) -> StrategyCandidateView:
    evaluation_plan = data.get("evaluation_plan", {})
    if not isinstance(evaluation_plan, Mapping):
        evaluation_plan = {}
    return StrategyCandidateView(
        candidate_id=str(data.get("candidate_id", "")),
        parent_strategy_id=str(data.get("parent_strategy_id", "")),
        iteration=int(data.get("iteration") or 0),
        applied_lesson_ids=tuple(
            str(item) for item in data.get("applied_lesson_ids", ())
        ),
        rerun_command=str(evaluation_plan.get("rerun_command", "")),
    )


def _leaderboard_run_from_mapping(data: Mapping[str, Any]) -> LeaderboardRunView:
    metrics = data.get("metrics")
    return LeaderboardRunView(
        rank=_int_value(data.get("rank"), 0),
        run_id=str(data.get("run_id", "")),
        scenario_id=str(data.get("scenario_id", "")),
        tool_regime_id=str(data.get("tool_regime_id", "unknown")),
        score=_float_value(data.get("score"), 0.0),
        outcome=str(data.get("outcome", "unknown")),
        deal_price=_optional_float(data.get("deal_price")),
        buyer_participant_id=str(data.get("buyer_participant_id", "unknown_buyer")),
        seller_participant_id=str(data.get("seller_participant_id", "unknown_seller")),
        metrics=_float_mapping(metrics if isinstance(metrics, Mapping) else {}),
    )


def _participant_coverage_from_mapping(
    data: Mapping[str, Any],
) -> ParticipantCoverageView:
    return ParticipantCoverageView(
        rank=_int_value(data.get("rank"), 0),
        participant_id=str(data.get("participant_id", "")),
        roles=_string_tuple(data.get("roles")),
        role_coverage=_float_value(data.get("role_coverage"), 0.0),
        unique_run_count=_int_value(data.get("unique_run_count"), 0),
        average_score=_float_value(data.get("average_score"), 0.0),
        coverage_adjusted_score=_float_value(
            data.get("coverage_adjusted_score"),
            0.0,
        ),
        balanced_average_score=_optional_float(data.get("balanced_average_score")),
    )


def _lesson_from_mapping(data: Mapping[str, Any]) -> BattleLessonView:
    evidence = data.get("evidence", ())
    return BattleLessonView(
        id=str(data.get("id", "")),
        severity=str(data.get("severity", "low")),
        category=str(data.get("category", "optimization")),
        finding=str(data.get("finding", "")),
        recommendation=str(data.get("recommendation", "")),
        suggested_strategy_patch=_optional_str(data.get("suggested_strategy_patch")),
        evidence=tuple(item for item in evidence if isinstance(item, Mapping)),
    )


def _evidence_label(item: Mapping[str, Any]) -> str:
    turn = item.get("turn", "?")
    role = item.get("role", "?")
    action = item.get("action_type", "?")
    return f"turn {turn} {role} {action}"


def _money_or_empty(value: float | None) -> str:
    return "n/a" if value is None else _money(value)


def _score_or_empty(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _money(value: float, currency: str = "USD") -> str:
    prefix = "$" if currency == "USD" else f"{currency} "
    return f"{prefix}{value:,.2f}"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _humanize(value: object) -> str:
    return str(value).replace("_", " ")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _int_value(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _float_value(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _float_mapping(values: Mapping[str, Any]) -> Mapping[str, float]:
    return {
        str(key): float(value)
        for key, value in values.items()
        if isinstance(value, (int, float))
    }


def _string_tuple(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value) for value in values)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
