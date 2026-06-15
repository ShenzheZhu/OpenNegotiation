"use strict";

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `${res.status} ${path}`);
  return data;
}

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => {
    v.hidden = v.id !== "view-" + name;
  });
  document.querySelectorAll("#nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });
  if (name === "match") refreshMatchOptions();
}

document.getElementById("nav").addEventListener("click", (e) => {
  if (e.target.dataset.view) showView(e.target.dataset.view);
});

// -- agent view ---------------------------------------------------------

async function refreshAgents() {
  const { agents } = await api("GET", "/api/agents");
  const list = document.getElementById("agent-list");
  list.innerHTML = "";
  for (const agent of agents) {
    const li = document.createElement("li");
    const keyNote = agent.has_key ? " (key set this session)" : "";
    li.textContent = `${agent.id} — ${agent.role}${keyNote}`;
    list.appendChild(li);
  }
  return agents;
}

document.getElementById("agent-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("agent-status");
  const form = e.target;
  const payload = {
    id: form.id.value,
    role: form.role.value,
    model: form.model.value || null,
    key: form.key.value || null,
    strategy_prompt: form.strategy_prompt.value,
  };
  try {
    const agent = await api("POST", "/api/agents", payload);
    form.key.value = ""; // never keep the key in the DOM
    setStatus(status, `Saved agent ${agent.id}.`, "ok");
    await refreshAgents();
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

// -- match view ---------------------------------------------------------

async function refreshMatchOptions() {
  const agents = await refreshAgents();
  const agentSel = document.getElementById("match-agent");
  agentSel.innerHTML = "";
  for (const agent of agents) {
    const opt = document.createElement("option");
    opt.value = agent.id;
    opt.textContent = `${agent.id} (${agent.role})`;
    agentSel.appendChild(opt);
  }
  const opponentSel = document.getElementById("match-opponent");
  if (opponentSel.options.length === 0) {
    const { profiles } = await api("GET", "/api/profiles");
    for (const p of profiles) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.name} [${p.role}, ${p.difficulty}]`;
      opponentSel.appendChild(opt);
    }
  }
}

function renderTrace(events) {
  const list = document.getElementById("trace");
  list.innerHTML = "";
  for (const ev of events) {
    const li = document.createElement("li");
    li.className = "role-" + ev.role;
    const parts = [`${ev.role} · ${ev.action_type}`];
    if (ev.offer && ev.offer.price != null) parts.push(`$${ev.offer.price}`);
    if (ev.tool_call) parts.push(`tool:${ev.tool_call.name}`);
    const head = document.createElement("div");
    head.textContent = parts.join("  ");
    li.appendChild(head);
    if (ev.content) {
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = ev.content;
      li.appendChild(meta);
    }
    if (ev.private) {
      const tag = document.createElement("div");
      tag.className = "private";
      tag.textContent = "private to actor";
      li.appendChild(tag);
    }
    list.appendChild(li);
  }
}

document.getElementById("match-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("match-status");
  const form = e.target;
  setStatus(status, "Running match…");
  document.getElementById("match-outcome").textContent = "";
  document.getElementById("trace").innerHTML = "";
  try {
    const match = await api("POST", "/api/matches", {
      agent_id: form.agent_id.value,
      opponent_profile_id: form.opponent_profile_id.value,
    });
    const price = match.deal_price != null ? ` at $${match.deal_price}` : "";
    document.getElementById("match-outcome").textContent =
      `Outcome: ${match.outcome}${price} (run ${match.run_id})`;
    setStatus(status, "Done.", "ok");
    const trace = await api("GET", `/api/runs/${match.run_id}/trace`);
    renderTrace(trace.events);
    window.lastRunId = match.run_id; // used by later views
  } catch (err) {
    setStatus(status, err.message, "err");
  }
});

refreshAgents().catch(() => {});
