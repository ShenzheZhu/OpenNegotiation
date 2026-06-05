"""Static HTML report generation for strategy sparring suites."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def write_sparring_report(summary_file: str | Path, output_file: str | Path) -> Path:
    """Write a dependency-free HTML report for a sparring suite artifact."""

    summary = _load_summary(summary_file)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _strip_trailing_whitespace(render_sparring_report(summary)),
        encoding="utf-8",
    )
    return output_path


def render_sparring_report(summary: Mapping[str, Any]) -> str:
    results = _mapping_list(summary.get("results"))
    title = "OpenNego Strategy Sparring"
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f6f3ec;
      --ink: #17201f;
      --muted: #66706d;
      --line: #d8ded9;
      --card: #ffffff;
      --accent: #256f67;
      --accent-2: #ad5a2a;
      --danger: #a33d35;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    .shell {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 40px; }}
    .hero {{
      display: grid;
      gap: 16px;
      padding: 36px 0 24px;
      border-bottom: 1px solid var(--line);
    }}
    .eyebrow {{ margin: 0; color: var(--accent); font-weight: 800; text-transform: uppercase; font-size: 12px; letter-spacing: 0; }}
    h1 {{ margin: 0; font-size: 58px; line-height: .98; max-width: 920px; }}
    h2 {{ margin: 0 0 12px; font-size: 26px; }}
    h3 {{ margin: 0 0 8px; font-size: 17px; }}
    p {{ margin: 0; }}
    .subtitle {{ max-width: 780px; color: var(--muted); font-size: 18px; }}
    .section {{ padding: 24px 0; border-bottom: 1px solid var(--line); }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .value {{ font-size: 24px; font-weight: 800; }}
    .pill {{ display: inline-block; padding: 3px 9px; border: 1px solid var(--line); border-radius: 999px; background: #fff; font-size: 12px; }}
    .muted {{ color: var(--muted); }}
    .score {{ color: var(--accent); font-weight: 800; }}
    .failed {{ color: var(--danger); font-weight: 800; }}
    .table-scroll {{ width: 100%; overflow-x: auto; }}
    table {{ width: 100%; min-width: 860px; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 11px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    @media (max-width: 760px) {{
      .grid {{ grid-template-columns: 1fr 1fr; }}
      .shell {{ width: min(100% - 24px, 1120px); }}
      h1 {{ font-size: 36px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">Strategy marketplace training loop</p>
      <h1>OpenNego strategy sparring report</h1>
      <p class="subtitle">A no-key curriculum view over marketplace NPC profiles, benchmark artifacts, and policy-learning battle reports.</p>
      <p><span class="pill">{_escape(summary.get("execution_mode"))}</span> <span class="pill">schema {_escape(summary.get("schema_version"))}</span></p>
    </section>

    <section class="section">
      <div class="grid">
        <div class="card"><div class="label">Profiles</div><div class="value">{_escape(summary.get("total_profiles"))}</div></div>
        <div class="card"><div class="label">Completed</div><div class="value">{_escape(summary.get("completed"))}</div></div>
        <div class="card"><div class="label">Failed</div><div class="value">{_escape(summary.get("failed"))}</div></div>
        <div class="card"><div class="label">User Role</div><div class="value">{_escape(summary.get("user_role"))}</div></div>
      </div>
    </section>

    <section class="section">
      <h2>NPC Profile Results</h2>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Profile</th>
              <th>Difficulty</th>
              <th>Status</th>
              <th>Outcome</th>
              <th>Policy Score</th>
              <th>Failure Modes</th>
              <th>Lessons</th>
              <th>Battle Report</th>
            </tr>
          </thead>
          <tbody>
            {_result_rows(results)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <h2>Boundary</h2>
      <p class="muted">This report is generated from local sparring artifacts. In profile-backed fixture sparring mode, selected NPC profiles are instantiated as deterministic counterparties, and their archetypes, expected traps, and trace evidence drive the battle report.</p>
    </section>
  </main>
</body>
</html>
"""


def _result_rows(results: Sequence[Mapping[str, Any]]) -> str:
    if not results:
        return '<tr><td colspan="8" class="muted">No sparring results recorded.</td></tr>'
    rows = []
    for result in results:
        status_class = "failed" if result.get("status") == "failed" else "score"
        rows.append(
            "<tr>"
            f"<td><strong>{_escape(result.get('profile_name'))}</strong><br><code>{_escape(result.get('profile_id'))}</code></td>"
            f"<td>{_escape(result.get('difficulty'))}</td>"
            f"<td class=\"{status_class}\">{_escape(result.get('status'))}</td>"
            f"<td>{_escape(result.get('outcome') or 'n/a')} {_money(result.get('deal_price'))}</td>"
            f"<td><span class=\"score\">{_escape(result.get('policy_score') or 'n/a')}</span></td>"
            f"<td>{_join(result.get('failure_modes'))}</td>"
            f"<td>{_join(result.get('lesson_ids'))}</td>"
            f"<td><code>{_escape(result.get('battle_report') or '')}</code></td>"
            "</tr>"
        )
    return "\n".join(rows)


def _load_summary(path: str | Path) -> Mapping[str, Any]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: expected JSON object")
    if data.get("schema_version") != "opennego.sparring_suite.v1":
        raise ValueError(f"{path}: expected opennego.sparring_suite.v1")
    return data


def _mapping_list(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _join(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ", ".join(_escape(item) for item in value)


def _money(value: object) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return f"at ${float(value):.2f}"


def _escape(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
