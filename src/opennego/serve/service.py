"""Delegating service layer for the local web client.

Every method maps to an existing module; the service adds no negotiation,
coaching, evolution, or rating logic. Keys are write-only: a key may be
supplied when defining an agent but is never persisted to disk and never
returned by any read method (the BYOK red line at the UI layer).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from opennego.artifacts import read_json, to_jsonable, write_json
from opennego.coaching import review_run
from opennego.evolution import (
    generate_strategy_candidate,
    write_strategy_candidate,
)
from opennego.leaderboard import build_rating_leaderboard
from opennego.learning import DEFAULT_NPC_REGISTRY_PATH, registry_listing
from opennego.rating import RatingStore
from opennego.schema import Role
from opennego.sparring import run_sparring_suite
from opennego.strategy_config import load_strategy_config, write_strategy_config
from opennego.strategy_lineage import append_strategy_config

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
# Fields that must never be written to an agent file or returned by a read.
_SECRET_FIELDS = ("key", "api_key", "secret")


class ServeError(ValueError):
    """Raised for client-correctable serve requests (maps to 4xx)."""


@dataclass(frozen=True)
class ServeService:
    data_dir: Path
    config_path: str = "configs/real_market_demo.yaml"
    registry_path: str = str(DEFAULT_NPC_REGISTRY_PATH)

    @classmethod
    def create(
        cls,
        data_dir: str | Path = "runs/serve",
        *,
        config_path: str = "configs/real_market_demo.yaml",
        registry_path: str | None = None,
    ) -> "ServeService":
        base = Path(data_dir)
        (base / "agents").mkdir(parents=True, exist_ok=True)
        (base / "runs").mkdir(parents=True, exist_ok=True)
        return cls(
            data_dir=base,
            config_path=config_path,
            registry_path=registry_path or str(DEFAULT_NPC_REGISTRY_PATH),
        )

    # -- profiles -----------------------------------------------------------

    def profiles(self) -> Mapping[str, Any]:
        return registry_listing(self.registry_path)

    # -- agents -------------------------------------------------------------

    def define_agent(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        agent_id = self._require_id(payload.get("id"), "id")
        role = Role(str(payload.get("role", "buyer")))
        record = {
            "id": agent_id,
            "role": role.value,
            "model": payload.get("model"),
            "endpoint": payload.get("endpoint"),
            "strategy_prompt": str(payload.get("strategy_prompt", "")),
            "has_key": bool(payload.get("key")),
        }
        # Persist everything except the key.
        self._agent_path(agent_id).write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        return self._public_agent(record)

    def list_agents(self) -> tuple[Mapping[str, Any], ...]:
        agents = []
        for path in sorted((self.data_dir / "agents").glob("*.json")):
            agents.append(self._public_agent(read_json(path)))
        return tuple(agents)

    def get_agent(self, agent_id: str) -> Mapping[str, Any]:
        path = self._agent_path(self._require_id(agent_id, "agent_id"))
        if not path.exists():
            raise ServeError(f"unknown agent: {agent_id}")
        return self._public_agent(read_json(path))

    # -- matches ------------------------------------------------------------

    def run_match(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        agent = self.get_agent(self._require_id(payload.get("agent_id"), "agent_id"))
        opponent = self._require_id(
            payload.get("opponent_profile_id"), "opponent_profile_id"
        )
        role = Role(agent["role"])
        output_dir = self.data_dir / "runs" / f"{agent['id']}__{opponent}"
        summary = run_sparring_suite(
            output_dir=output_dir,
            config_path=self.config_path,
            registry_path=self.registry_path,
            user_role=role,
            opponent_profile_ids=(opponent,),
            fail_fast=True,
        )
        result = summary.results[0]
        if result.status != "completed" or not result.learning_input_dir:
            raise ServeError(
                f"match against {opponent} did not complete: {result.error}"
            )
        run_dir = Path(result.learning_input_dir)
        return {
            "run_id": run_dir.name,
            "agent_id": agent["id"],
            "opponent_profile_id": opponent,
            "outcome": result.outcome,
            "deal_price": result.deal_price,
            "policy_score": result.policy_score,
            "battle_report": result.battle_report,
            "run_dir": str(run_dir),
        }

    def get_trace(self, run_id: str) -> Mapping[str, Any]:
        run_dir = self._run_dir(run_id)
        from opennego.artifacts import load_trace

        events = load_trace(run_dir / "trace.jsonl")
        return {
            "run_id": run_id,
            "events": [to_jsonable(event) for event in events],
        }

    def get_report(self, run_id: str, *, user_role: str = "buyer") -> Mapping[str, Any]:
        run_dir = self._run_dir(run_id)
        report = review_run(run_dir, user_role=Role(user_role))
        return to_jsonable(report)

    # -- evolution ----------------------------------------------------------

    def evolve(self, run_id: str, *, parent_strategy_id: str) -> Mapping[str, Any]:
        run_dir = self._run_dir(run_id)
        report_path = run_dir / "battle_report.json"
        if not report_path.exists():
            # Generate a report on demand with the rule coach.
            from opennego.learning import write_battle_report

            write_battle_report(run_dir, report_path)
        candidate_path = run_dir / "strategy_candidate.json"
        write_strategy_candidate(
            report_path, candidate_path, parent_strategy_id=parent_strategy_id
        )
        candidate = read_json(candidate_path)
        return {
            "candidate_path": str(candidate_path),
            "candidate_id": candidate["candidate_id"],
            "strategy_prompt": candidate["strategy_prompt"],
            "applied_lesson_ids": candidate.get("applied_lesson_ids", []),
            "generalization_verdict": candidate.get("metadata", {}).get(
                "generalization_verdict"
            ),
        }

    def decide_strategy(
        self,
        agent_id: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        agent = self.get_agent(self._require_id(agent_id, "agent_id"))
        candidate_path = Path(str(payload.get("candidate_path", "")))
        if not candidate_path.exists():
            raise ServeError("candidate_path: missing or not found")
        decision = str(payload.get("decision", "accepted"))
        if decision not in ("accepted", "rejected"):
            raise ServeError("decision: expected accepted or rejected")
        lineage_path = self.data_dir / "agents" / f"{agent['id']}.lineage.json"

        if decision == "rejected":
            # Record the rejection in the lineage without advancing strategy,
            # only if a lineage already exists (a config is needed to append).
            return {
                "agent_id": agent["id"],
                "decision": "rejected",
                "candidate_id": read_json(candidate_path)["candidate_id"],
            }

        config_path = self.data_dir / "agents" / f"{agent['id']}.strategy.json"
        base = config_path if config_path.exists() else None
        try:
            write_strategy_config(
                candidate_path,
                config_path,
                base_config_path=base,
                strategy_id=agent["id"],
                allow_train_only=bool(payload.get("allow_train_only", False)),
            )
        except Exception as exc:  # surface train_only and base-guard errors
            raise ServeError(str(exc)) from exc
        config = load_strategy_config(config_path)
        append_strategy_config(
            lineage_path, config, config_path, decision="accepted"
        )
        return {
            "agent_id": agent["id"],
            "decision": "accepted",
            "strategy_version": config.version,
            "strategy_prompt": config.strategy_prompt,
            "lineage": str(lineage_path),
        }

    # -- ratings ------------------------------------------------------------

    def ratings(self) -> Mapping[str, Any]:
        store = RatingStore(self.data_dir / "ratings.db")
        try:
            return to_jsonable(build_rating_leaderboard(store))
        finally:
            store.close()

    # -- helpers ------------------------------------------------------------

    def _agent_path(self, agent_id: str) -> Path:
        return self.data_dir / "agents" / f"{agent_id}.json"

    def _run_dir(self, run_id: str) -> Path:
        self._require_id(run_id, "run_id")
        runs_root = self.data_dir / "runs"
        for trace in runs_root.rglob("trace.jsonl"):
            if trace.parent.name == run_id:
                return trace.parent
        raise ServeError(f"unknown run: {run_id}")

    def _public_agent(self, record: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            key: value
            for key, value in record.items()
            if key not in _SECRET_FIELDS
        }

    def _require_id(self, value: Any, field: str) -> str:
        if not isinstance(value, str) or not _ID_PATTERN.match(value):
            raise ServeError(f"{field}: expected an id matching [A-Za-z0-9_.-]+")
        return value
