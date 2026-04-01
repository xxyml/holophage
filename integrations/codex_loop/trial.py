from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.codex_loop.autopilot import select_next_task
from integrations.codex_loop.constants import INTERVENTION_POLICY_PATH
from integrations.codex_loop.governor import get_current_state, get_runtime_policy, get_task_record
from integrations.codex_loop.project_profile import get_allowed_unattended_workflows
from integrations.codex_loop.schemas import write_json


def materialize_policy_defaults() -> Path:
    policy = get_runtime_policy()
    write_json(INTERVENTION_POLICY_PATH, policy)
    return INTERVENTION_POLICY_PATH


def _results_closeout_artifact_status(task_record: dict[str, Any]) -> dict[str, Any]:
    objective = str(task_record.get("objective", ""))
    details = {
        "requires_artifact_review": task_record.get("workflow_kind") == "results_closeout",
        "objective": objective,
    }
    return details


def trial_precheck(task_id: str = "") -> dict[str, Any]:
    policy = get_runtime_policy()
    state = get_current_state()
    next_task = select_next_task(policy)
    target_task = get_task_record(task_id) if task_id else next_task
    allowed = set(get_allowed_unattended_workflows(policy))
    checks = {
        "policy_materialized_shape": all(
            key in policy
            for key in (
                "allowed_unattended_workflow_kinds",
                "default_unattended_risk_level",
                "max_retries_per_task",
                "stale_after_seconds",
            )
        ),
        "lease_ready": not bool(state.get("runner_id")) or not bool(state.get("active_lease_status")),
        "next_task_matches_target": bool(target_task) and bool(next_task) and target_task["task_id"] == next_task["task_id"],
    }
    target_summary: dict[str, Any] = {}
    if target_task:
        target_summary = {
            "task_id": target_task["task_id"],
            "status": target_task["status"],
            "workflow_kind": target_task["workflow_kind"],
            "risk_level": target_task["risk_level"],
            "autopilot_enabled": bool(target_task.get("autopilot_enabled", True)),
            "workflow_allowed": str(target_task["workflow_kind"]) in allowed,
            "cooldown_until": str(target_task.get("cooldown_until", "")),
            "artifact_status": _results_closeout_artifact_status(target_task),
        }
        checks["target_task_ready"] = (
            str(target_task["status"]) == "ready"
            and bool(target_task.get("autopilot_enabled", True))
            and str(target_task["workflow_kind"]) in allowed
            and str(target_task["risk_level"]) == str(policy.get("default_unattended_risk_level", "low"))
            and not str(target_task.get("cooldown_until", "")).strip()
        )
    else:
        checks["target_task_ready"] = False
    return {
        "state": state,
        "policy": policy,
        "next_task_id": next_task["task_id"] if next_task else "",
        "target_task": target_summary,
        "checks": checks,
    }
