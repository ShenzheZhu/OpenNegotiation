"""Static HTML report generation for small OpenNego demos."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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


@dataclass(frozen=True)
class DemoRun:
    output_dir: Path
    manifest: RunManifest
    scenario: ScenarioArtifact
    metrics: MetricReport
    trace: Sequence[TraceEventRecord]


def write_demo_report(input_dir: str | Path, output_file: str | Path) -> Path:
    """Write a static HTML dashboard for a small benchmark artifact directory."""

    runs = load_demo_runs(input_dir)
    if not runs:
        raise ValueError(f"{input_dir}: no benchmark run artifacts found")
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_demo_report(runs), encoding="utf-8")
    return output_path


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


def render_demo_report(runs: Sequence[DemoRun]) -> str:
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
  <title>OpenNego Demo Dashboard</title>
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
    .card {{ padding: 16px; background: var(--soft); border: 1px solid var(--line); border-radius: 8px; }}
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
      .hero, .grid-3, .flow, .figure-grid, .kpis {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 36px; }}
      .section-head {{ align-items: flex-start; flex-direction: column; }}
      .kpi .value {{ font-size: 20px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <nav class="nav">
      <a class="brand" href="#">OpenNego</a>
      <div class="navlinks">
        <a href="#overview">Overview</a>
        <a href="#mechanism">Mechanism</a>
        <a href="#leaderboard">Leaderboard</a>
        <a href="#trace">Trace</a>
        <a href="#findings">Findings</a>
      </div>
    </nav>
  </header>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">Agentic negotiation benchmark</p>
      <h1>Benchmarking AI agents in real-market negotiation and transaction settings</h1>
      <p class="subtitle">OpenNego evaluates how buyer and seller agents search market evidence, bargain under asymmetric tools, and settle realistic consumer-to-consumer deals.</p>
      <div class="actions">
        <a class="button primary" href="#leaderboard">View leaderboard preview</a>
        <a class="button" href="#overview">Explore mechanism</a>
        <a class="button" href="../../docs/real_market_benchmark_design.md">Design notes</a>
      </div>
      <div class="kpis">
        <div class="kpi"><div class="label">Demo Runs</div><div class="value">{len(runs)}</div></div>
        <div class="kpi"><div class="label">Product Cluster</div><div class="value">{_escape(_humanize(product.condition))}</div></div>
        <div class="kpi"><div class="label">Market Reference</div><div class="value">{reference_price}</div></div>
        <div class="kpi"><div class="label">Sold Comps</div><div class="value">{_escape(sample_size)}</div></div>
      </div>
    </section>

    <section id="overview" class="section">
      <div class="section-head">
        <div>
          <h2>OpenNego Overview</h2>
          <p class="section-copy">A market lifecycle view of negotiation: agents do not just chat, they gather evidence, make structured offers, and pass accepted deals through transaction validation.</p>
        </div>
        <span class="pill">Artifact-backed demo</span>
      </div>
      <div class="overview-figure">
        <div class="figure-grid">
          <div class="figure-node"><strong>Buyer Agent</strong><span class="muted">Budget, preferences, search tools, and offer policy.</span></div>
          <div class="figure-node"><strong>Market Evidence</strong><span class="muted">Sold comps, provenance, noisy/stale/failure regimes.</span></div>
          <div class="figure-node"><strong>Negotiation Protocol</strong><span class="muted">Messages, offers, accepts, rejects, and private tool traces.</span></div>
          <div class="figure-node"><strong>Transaction Layer</strong><span class="muted">Shipping, tax, fees, escrow, payment, and risk outcomes.</span></div>
        </div>
        <p class="figure-caption">The public benchmark reads versioned artifacts: scenario, manifest, trace JSONL, and metrics.</p>
      </div>
    </section>

    <section class="section">
      <h2>Why Choose OpenNego</h2>
      <div class="grid-3">
        <div class="card"><h3>Agentic, not prompt-only</h3><p class="muted">Agents can use tools for market search, provenance checks, and transaction reasoning before making offers.</p></div>
        <div class="card"><h3>Market-grounded</h3><p class="muted">Scenarios are anchored to comparable sale distributions instead of assuming a hidden human cost price.</p></div>
        <div class="card"><h3>Transaction-aware</h3><p class="muted">Accepted offers can be settled through shipping, tax, fees, escrow, payment, and risk simulators.</p></div>
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
            {_leaderboard_rows(leaderboard)}
          </tbody>
        </table>
      </div>
    </section>

    <section id="findings" class="section">
      <h2>Key Findings From This Smoke</h2>
      <div class="grid-3">
        <div class="card"><h3>Tools change price formation</h3><p class="muted">The buyer-private market tool pulls offers toward the sold-comparable reference instead of the inflated asking price.</p></div>
        <div class="card"><h3>Noisy evidence remains visible</h3><p class="muted">Tool regime metadata and trace provenance make clean, noisy, stale, adversarial, and failure cases auditable.</p></div>
        <div class="card"><h3>Transactions are part of eval</h3><p class="muted">The accepted offer is not the final story: buyer total cost, seller net revenue, fees, and risk are separately scored.</p></div>
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
      Generated from OpenNego benchmark artifacts. This is a no-key demo surface, not a live marketplace collection.
    </footer>
  </main>
</body>
</html>
"""


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


def _money_or_empty(value: float | None) -> str:
    return "n/a" if value is None else _money(value)


def _money(value: float, currency: str = "USD") -> str:
    prefix = "$" if currency == "USD" else f"{currency} "
    return f"{prefix}{value:,.2f}"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _humanize(value: object) -> str:
    return str(value).replace("_", " ")
