import json

import pytest

from opennego.serve.app import dispatch
from opennego.serve.service import ServeError, ServeService


def _service(tmp_path):
    return ServeService.create(tmp_path / "serve")


def test_health_and_profiles(tmp_path):
    service = _service(tmp_path)
    status, health = dispatch(service, "GET", "/api/health")
    assert status == 200 and health["status"] == "ok"

    status, profiles = dispatch(service, "GET", "/api/profiles")
    assert status == 200
    assert any(p["id"] == "seller_hardline_anchor_v1" for p in profiles["profiles"])


def test_define_agent_never_returns_or_persists_key(tmp_path):
    service = _service(tmp_path)
    status, agent = dispatch(
        service,
        "POST",
        "/api/agents",
        {
            "id": "my_buyer",
            "role": "buyer",
            "model": "openrouter/x",
            "key": "sk-secret-value",
            "strategy_prompt": "Anchor on comps.",
        },
    )
    assert status == 200
    assert "key" not in agent
    assert agent["has_key"] is True

    # Not returned by GET.
    _, fetched = dispatch(service, "GET", "/api/agents/my_buyer")
    assert "key" not in fetched
    # Not on disk in any form.
    on_disk = (tmp_path / "serve" / "agents" / "my_buyer.json").read_text()
    assert "sk-secret-value" not in on_disk


def test_define_agent_rejects_bad_id(tmp_path):
    service = _service(tmp_path)
    status, payload = dispatch(
        service, "POST", "/api/agents", {"id": "../escape", "role": "buyer"}
    )
    assert status == 400
    assert "id" in payload["error"]


def test_run_match_trace_and_report(tmp_path):
    service = _service(tmp_path)
    dispatch(
        service, "POST", "/api/agents",
        {"id": "buyer1", "role": "buyer", "strategy_prompt": "p"},
    )
    status, match = dispatch(
        service, "POST", "/api/matches",
        {"agent_id": "buyer1", "opponent_profile_id": "seller_hardline_anchor_v1"},
    )
    assert status == 200
    run_id = match["run_id"]

    status, trace = dispatch(service, "GET", f"/api/runs/{run_id}/trace")
    assert status == 200 and trace["events"]

    status, report = dispatch(service, "GET", f"/api/runs/{run_id}/report")
    assert status == 200
    assert report["schema_version"] == "opennego.battle_report.v2"


def test_evolve_and_accept_advances_strategy_with_lineage(tmp_path):
    service = _service(tmp_path)
    dispatch(service, "POST", "/api/agents",
             {"id": "buyer1", "role": "buyer", "strategy_prompt": "p"})
    _, match = dispatch(
        service, "POST", "/api/matches",
        {"agent_id": "buyer1", "opponent_profile_id": "seller_hardline_anchor_v1"},
    )
    run_id = match["run_id"]

    status, candidate = dispatch(
        service, "POST", f"/api/runs/{run_id}/evolve",
        {"parent_strategy_id": "buyer1"},
    )
    assert status == 200 and candidate["candidate_id"]

    status, decision = dispatch(
        service, "POST", "/api/agents/buyer1/strategy",
        {"candidate_path": candidate["candidate_path"], "decision": "accepted"},
    )
    assert status == 200
    assert decision["decision"] == "accepted"
    assert decision["strategy_version"] >= 1
    lineage = json.loads((tmp_path / "serve" / "agents" / "buyer1.lineage.json").read_text())
    assert lineage["nodes"][0]["decision"] == "accepted"


def test_reject_does_not_advance_strategy(tmp_path):
    service = _service(tmp_path)
    dispatch(service, "POST", "/api/agents",
             {"id": "buyer1", "role": "buyer", "strategy_prompt": "p"})
    _, match = dispatch(
        service, "POST", "/api/matches",
        {"agent_id": "buyer1", "opponent_profile_id": "seller_hardline_anchor_v1"},
    )
    _, candidate = dispatch(
        service, "POST", f"/api/runs/{match['run_id']}/evolve",
        {"parent_strategy_id": "buyer1"},
    )
    status, decision = dispatch(
        service, "POST", "/api/agents/buyer1/strategy",
        {"candidate_path": candidate["candidate_path"], "decision": "rejected"},
    )
    assert status == 200 and decision["decision"] == "rejected"
    assert not (tmp_path / "serve" / "agents" / "buyer1.strategy.json").exists()


def test_ratings_endpoint_returns_v2(tmp_path):
    service = _service(tmp_path)
    status, ratings = dispatch(service, "GET", "/api/ratings")
    assert status == 200
    assert ratings["schema_version"] == "opennego.leaderboard.v2"


def test_unknown_route_is_404(tmp_path):
    service = _service(tmp_path)
    status, payload = dispatch(service, "GET", "/api/nope")
    assert status == 404
    assert "no route" in payload["error"]


def test_unknown_run_is_400(tmp_path):
    service = _service(tmp_path)
    status, payload = dispatch(service, "GET", "/api/runs/does_not_exist/trace")
    assert status == 400
    assert "unknown run" in payload["error"]


def test_placeholder_static_index_is_present():
    from opennego.serve.app import PLACEHOLDER_STATIC_DIR

    index = PLACEHOLDER_STATIC_DIR / "index.html"
    assert index.is_file()
    assert "OpenNegotiation" in index.read_text()


def test_resolve_static_dir_prefers_built_web_dist():
    from opennego.serve.app import PLACEHOLDER_STATIC_DIR, resolve_static_dir

    static_dir = resolve_static_dir()
    # In a source checkout with the client built, web/dist wins; otherwise the
    # packaged placeholder is used. Either way it holds an index.html.
    assert (static_dir / "index.html").is_file()
    if static_dir != PLACEHOLDER_STATIC_DIR:
        assert static_dir.name == "dist"
        assert static_dir.parent.name == "web"
