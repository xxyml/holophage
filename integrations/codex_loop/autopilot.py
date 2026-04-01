from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import time
from time import perf_counter
from typing import Any
from uuid import uuid4

from integrations.codex_loop.constants import (
    AUTOCONTINUE_WORKFLOW_KINDS,
    CURRENT_SPRINT_PATH,
    CURRENT_STATE_PATH,
    DEFAULT_INTERVENTION_POLICY,
    RUNTIME_SESSION_HISTORY_PATH,
    RUNTIME_SESSION_PATH,
    LOOP_RUNS_DIR,
    FORBIDDEN_WRITE_TOKENS,
    EXECUTION_RESULT_NAME,
    PLANNER_DECISION_NAME,
    PLANNER_PACKET_NAME,
    REVIEW_VERDICT_NAME,
    TASK_TYPE_TO_SKILL,
)
from integrations.codex_loop.checkpoint import load_stage_checkpoint, write_stage_checkpoint
from integrations.codex_loop.events import append_event
from integrations.codex_loop.governor import (
    GovernorError,
    _canonical_reason_code,
    advance_review,
    get_current_state,
    get_runtime_policy,
    get_task_record,
    list_task_records,
    pause_task,
    prepare_executor_workspace,
    prepare_experiment_workspace,
    prepare_implementation_workspace,
    prepare_plan_packet,
    prepare_planner_workspace,
    prepare_review_verdict_template,
    prepare_reviewer_workspace,
    run_execution,
    save_task_record,
    sync_experiment_from_run,
)
from integrations.codex_loop.project_profile import (
    get_allowed_unattended_workflows,
    is_progress_meaningful,
    is_task_in_cooldown,
    task_priority_key,
)
from integrations.codex_loop.program_planner import ensure_program_progress, show_budget_state, show_program_handoff, show_program_status
from integrations.codex_loop.queue_planner import plan_queue, show_queue_plan
from integrations.codex_loop.runtime_scheduler import (
    append_jsonl,
    cooldown_ready_task_ids,
    task_registry_signature,
    wake_reason_for_cycle,
)
from integrations.codex_loop.schemas import (
    default_runtime_session,
    load_json,
    validate_current_state,
    validate_planner_decision,
    validate_review_verdict,
    validate_runtime_session,
    write_json,
)
from integrations.codex_loop.workflow_registry import show_workflow_status


def _now() -> datetime:
    return datetime.now().astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _load_state() -> dict[str, Any]:
    return get_current_state()


def _write_state(state: dict[str, Any]) -> None:
    write_json(CURRENT_STATE_PATH, validate_current_state(state).data)


def _load_runtime_session() -> dict[str, Any]:
    try:
        return validate_runtime_session(load_json(RUNTIME_SESSION_PATH)).data
    except Exception:
        return validate_runtime_session(default_runtime_session()).data


def _write_runtime_session(session: dict[str, Any]) -> None:
    write_json(RUNTIME_SESSION_PATH, validate_runtime_session(session).data)


def _session_snapshot(*, runner_id: str, started_at: str = "", last_heartbeat_at: str = "", rounds_completed: int = 0, idle_cycles: int = 0, last_wake_reason: str = "", session_end_reason: str = "", last_run_id: str = "", last_task_id: str = "") -> dict[str, Any]:
    payload = default_runtime_session()
    payload.update(
        {
            "runner_id": runner_id,
            "started_at": started_at,
            "last_heartbeat_at": last_heartbeat_at,
            "rounds_completed": rounds_completed,
            "idle_cycles": idle_cycles,
            "last_wake_reason": last_wake_reason,
            "session_end_reason": session_end_reason,
            "last_run_id": last_run_id,
            "last_task_id": last_task_id,
        }
    )
    return payload


def _safe_status_call(fn: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        result = fn()
        return result if isinstance(result, dict) else dict(fallback)
    except Exception:
        return dict(fallback)


def _program_waiting_stop_reason() -> str:
    program_state = _safe_status_call(show_program_status, {})
    program_handoff = _safe_status_call(show_program_handoff, {})
    workflow_status = _safe_status_call(show_workflow_status, {"workflow": {}})
    workflow_payload = workflow_status.get("workflow", {}) if isinstance(workflow_status, dict) else {}
    active_workflow_id = str(program_state.get("active_workflow_id", "")).strip()
    active_workflow_status = str(workflow_payload.get("status", "")).strip()
    next_recommended_workflow = str(program_handoff.get("next_recommended_workflow", "") or program_state.get("next_recommended_workflow", "")).strip()
    next_ready_task_id = str(program_handoff.get("next_ready_task_id", "")).strip()
    program_status = str(program_state.get("status", "")).strip()
    completed_milestones = list(program_state.get("completed_milestones", [])) if isinstance(program_state.get("completed_milestones", []), list) else []
    active_milestone = str(program_state.get("active_milestone", "")).strip()
    meaningful_program_state = bool(completed_milestones or active_milestone or next_recommended_workflow or next_ready_task_id)
    if active_workflow_id and active_workflow_status == "active":
        return ""
    if not meaningful_program_state:
        return ""
    if program_status == "completed":
        return "program_completed"
    if program_status == "paused_for_human" and (next_recommended_workflow or next_ready_task_id):
        return "program_waiting_for_next_phase"
    return ""


def _new_runner_id() -> str:
    return f"autopilot-{uuid4().hex[:8]}"


def _read_current_sprint_text() -> str:
    return CURRENT_SPRINT_PATH.read_text(encoding="utf-8") if CURRENT_SPRINT_PATH.exists() else ""


def _is_stale(state: dict[str, Any], policy: dict[str, Any], *, now: datetime) -> bool:
    heartbeat = str(state.get("heartbeat_at", "")).strip()
    if not heartbeat:
        return False
    try:
        heartbeat_at = datetime.fromisoformat(heartbeat)
    except ValueError:
        return False
    threshold = int(policy.get("stale_after_seconds", DEFAULT_INTERVENTION_POLICY["stale_after_seconds"]))
    return (now - heartbeat_at).total_seconds() > threshold


def _acquire_lease(runner_id: str, policy: dict[str, Any], *, allow_stale_takeover: bool) -> dict[str, Any]:
    state = _load_state()
    now = _now()
    current_runner = str(state.get("runner_id", "")).strip()
    if current_runner and current_runner != runner_id:
        stale = _is_stale(state, policy, now=now)
        if not stale or not allow_stale_takeover:
            raise GovernorError(f"runner lease held by `{current_runner}`.")
        append_event(
            "stale_detected",
            runner_id=runner_id,
            task_id=str(state.get("active_task_id", "")),
            run_id=str(state.get("current_run_id", "")),
            state_status=str(state.get("status", "")),
            reason_code="stale_detected",
            details={"previous_runner_id": current_runner},
        )

    state["runner_id"] = runner_id
    state["lease_acquired_at"] = now.isoformat(timespec="seconds")
    state["heartbeat_at"] = now.isoformat(timespec="seconds")
    state["stale_after_seconds"] = int(policy.get("stale_after_seconds", DEFAULT_INTERVENTION_POLICY["stale_after_seconds"]))
    state["active_lease_status"] = "active"
    _write_state(state)
    return state


def _heartbeat(runner_id: str) -> dict[str, Any]:
    state = _load_state()
    if str(state.get("runner_id", "")) != runner_id:
        raise GovernorError("runner lease mismatch during heartbeat.")
    state["heartbeat_at"] = _now_iso()
    _write_state(state)
    append_event(
        "runner_heartbeat",
        runner_id=runner_id,
        task_id=str(state.get("active_task_id", "")),
        run_id=str(state.get("current_run_id", "")),
        state_status=str(state.get("status", "")),
    )
    return state


def _release_lease(runner_id: str, *, status: str = "idle") -> None:
    state = _load_state()
    if str(state.get("runner_id", "")) != runner_id:
        return
    if status == "idle":
        state["runner_id"] = ""
        state["lease_acquired_at"] = ""
    state["active_lease_status"] = status
    state["heartbeat_at"] = _now_iso()
    _write_state(state)


def _append_session_history(session: dict[str, Any], *, unresolved: dict[str, Any] | None = None) -> None:
    payload = dict(validate_runtime_session(session).data)
    payload["recorded_at"] = _now_iso()
    payload["unresolved"] = dict(unresolved or {})
    append_jsonl(RUNTIME_SESSION_HISTORY_PATH, payload)


def _checkpoint_stage(runner_id: str, run_id: str, task_id: str, stage: str, state_status: str, resume_hint: str) -> None:
    write_stage_checkpoint(
        _run_dir(run_id),
        run_id=run_id,
        task_id=task_id,
        runner_id=runner_id,
        stage=stage,
        state_status=state_status,
        resume_hint=resume_hint,
    )


def _run_dir(run_id: str) -> Path:
    return LOOP_RUNS_DIR / run_id


def _event_pause_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    suggested_next_actions = [str(item) for item in payload.get("suggested_next_actions", []) if str(item).strip()]
    blocked_reason_detail = str(payload.get("blocked_reason_detail", "")).strip()
    details: dict[str, Any] = {}
    if blocked_reason_detail:
        details["blocked_reason_detail"] = blocked_reason_detail
    return {
        "details": details,
        "suggested_next_actions": suggested_next_actions,
    }


def _event_recovery_fields(result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    recovered_stage = str(result.get("recovered_stage", "")).strip()
    resume_action = str(result.get("resume_action", "")).strip()
    artifacts_verified = dict(result.get("artifacts_verified", {}))
    details: dict[str, Any] = {
        "recovered_stage": recovered_stage,
        "resume_action": resume_action,
        "artifacts_verified": artifacts_verified,
    }
    if recovered_stage or resume_action:
        details["recovery_summary"] = " -> ".join(item for item in (recovered_stage, resume_action) if item)
    return details


def _increment_attempt(task_record: dict[str, Any]) -> dict[str, Any]:
    task_record["retry_count"] = int(task_record.get("retry_count", 0)) + 1
    task_record["last_attempt_at"] = _now_iso()
    task_record["updated_at"] = _now_iso()
    return task_record


def _pause_due_to_retry_limit(task_record: dict[str, Any], policy: dict[str, Any]) -> None:
    max_retries = int(policy.get("max_retries_per_task", DEFAULT_INTERVENTION_POLICY["max_retries_per_task"]))
    if int(task_record.get("retry_count", 0)) <= max_retries:
        return
    pause_task(task_record["task_id"], "autopilot_max_retries_exceeded", reason_code="autopilot_max_retries_exceeded")
    paused_record = get_task_record(task_record["task_id"])
    pause_fields = _event_pause_fields(paused_record)
    append_event(
        "policy_blocked",
        task_id=task_record["task_id"],
        state_status="paused_for_human",
        details={
            "reason": "autopilot_max_retries_exceeded",
            "recommended_action_summary": pause_fields["suggested_next_actions"][0] if pause_fields["suggested_next_actions"] else "",
            **pause_fields["details"],
        },
        suggested_next_actions=pause_fields["suggested_next_actions"],
        reason_code="autopilot_max_retries_exceeded",
    )


def _autoplan_decision(task_record: dict[str, Any], run_id: str, phase: str) -> dict[str, Any]:
    workflow_kind = str(task_record["workflow_kind"])
    if workflow_kind == "implementation_task":
        action_kind = "implementation"
        action_name = "implementation-task"
        task_type = ""
        required_checks = list(task_record.get("required_checks", []))
        action_args = dict(TASK_TYPE_TO_SKILL.get(workflow_kind, {}).get("default_args", {}))
    elif workflow_kind == "experiment_run":
        action_kind = "experiment"
        action_name = "experiment-run"
        task_type = ""
        required_checks = list(task_record.get("required_checks", []))
        action_args = {
            "command": str(task_record.get("experiment_command", "")),
            "run_dir": str(task_record.get("experiment_run_dir", "")),
            "config_path": str(task_record.get("experiment_config_path", "")),
        }
    else:
        action_kind = "artifact_repair" if workflow_kind == "artifact_repair" else "skill"
        action_name = TASK_TYPE_TO_SKILL[workflow_kind]["skill"]
        task_type = workflow_kind
        required_checks = []
        action_args = dict(TASK_TYPE_TO_SKILL.get(workflow_kind, {}).get("default_args", {}))
        action_args.update(dict(task_record.get("skill_args", {})))
    return validate_planner_decision(
        {
            "schema_version": 2,
            "run_id": run_id,
            "task_id": task_record["task_id"],
            "phase": phase or "general_execution",
            "workflow_kind": workflow_kind,
            "task_type": task_type,
            "objective": task_record["objective"],
            "preflight_required": True,
            "action": {
                "kind": action_kind,
                "name": action_name,
                "args": action_args,
            },
            "success_criteria": list(task_record.get("success_criteria") or [f"Complete `{workflow_kind}` without fail-fast conditions."]),
            "fail_fast_conditions": ["active_truth_conflict", "planner_gate"],
            "review_focus": ["Confirm the workflow completed cleanly and produced the expected artifact state."],
            "risk_level": str(task_record.get("risk_level", "low")),
            "needs_human_before_execute": False,
            "allowed_write_paths": list(task_record.get("allowed_write_paths", [])),
            "required_checks": required_checks,
            "experiment_required_artifacts": list(task_record.get("experiment_required_artifacts", [])),
            "linked_experiment_id": "",
            "autocontinue_eligible": workflow_kind in AUTOCONTINUE_WORKFLOW_KINDS,
        }
    ).data


def _implementation_autopilot_allowed(task_record: dict[str, Any], policy: dict[str, Any]) -> bool:
    if str(task_record.get("workflow_kind")) != "implementation_task":
        return False
    if not bool(policy.get("allow_unattended_implementation", False)):
        return False
    if str(task_record.get("risk_level", "")) != str(policy.get("default_unattended_risk_level", "low")):
        return False
    allowed_write_paths = [str(item).replace("\\", "/") for item in task_record.get("allowed_write_paths", [])]
    if not allowed_write_paths:
        return False
    normalized_paths = [item.lower() for item in allowed_write_paths]
    if any(any(token in item for token in FORBIDDEN_WRITE_TOKENS) for item in normalized_paths):
        return False
    required_checks = [str(item).strip() for item in task_record.get("required_checks", []) if str(item).strip()]
    if not required_checks:
        return False
    return True


def _experiment_autopilot_allowed(task_record: dict[str, Any], policy: dict[str, Any]) -> bool:
    if str(task_record.get("workflow_kind")) != "experiment_run":
        return False
    if not bool(policy.get("allow_unattended_experiment", False)):
        return False
    if str(task_record.get("risk_level", "")) != str(policy.get("default_unattended_risk_level", "low")):
        return False
    if not [str(item).strip() for item in task_record.get("required_checks", []) if str(item).strip()]:
        return False
    if not str(task_record.get("experiment_command", "")).strip():
        return False
    if not str(task_record.get("experiment_run_dir", "")).strip():
        return False
    return True


def _write_review_verdict_from_template(template_path: Path) -> Path:
    verdict = validate_review_verdict(load_json(template_path)).data
    output_path = template_path.parent / REVIEW_VERDICT_NAME
    write_json(output_path, verdict)
    return output_path


def _gate_task(task_record: dict[str, Any], reason: str, *, runner_id: str) -> None:
    pause_task(task_record["task_id"], reason, reason_code=reason)
    paused_record = get_task_record(task_record["task_id"])
    pause_fields = _event_pause_fields(paused_record)
    append_event(
        "policy_blocked",
        runner_id=runner_id,
        task_id=task_record["task_id"],
        state_status="paused_for_human",
        reason_code=reason,
        details={
            "reason": reason,
            "recommended_action_summary": pause_fields["suggested_next_actions"][0] if pause_fields["suggested_next_actions"] else "",
            **pause_fields["details"],
        },
        suggested_next_actions=pause_fields["suggested_next_actions"],
    )


def select_next_task(policy: dict[str, Any] | None = None) -> dict[str, Any] | None:
    policy = policy or get_runtime_policy()
    now_iso = _now_iso()
    current_sprint_text = _read_current_sprint_text()
    allowed_unattended = set(get_allowed_unattended_workflows(policy))
    risk_level = str(policy.get("default_unattended_risk_level", "low"))
    candidates: list[dict[str, Any]] = []
    for task_record in list_task_records():
        if str(task_record.get("status")) != "ready":
            continue
        if not bool(task_record.get("autopilot_enabled", True)):
            continue
        workflow_kind = str(task_record.get("workflow_kind"))
        if workflow_kind == "implementation_task":
            if not _implementation_autopilot_allowed(task_record, policy):
                continue
        elif workflow_kind == "experiment_run":
            if not _experiment_autopilot_allowed(task_record, policy):
                continue
        elif workflow_kind not in allowed_unattended:
            continue
        if str(task_record.get("risk_level", "")) != risk_level:
            continue
        if is_task_in_cooldown(task_record, now_iso=now_iso):
            continue
        candidates.append(task_record)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: task_priority_key(item, current_sprint_text))[0]


def show_loop_status() -> dict[str, Any]:
    state = _load_state()
    policy = get_runtime_policy()
    runtime_session = _load_runtime_session()
    queue_plan = _safe_status_call(show_queue_plan, {"enabled": False, "state": {"last_planner_run_at": "", "last_generated_task_ids": []}, "workflow": {}, "candidates": []})
    workflow_status = _safe_status_call(show_workflow_status, {"workflow": {}, "program": {}, "templates": {}})
    program_state = _safe_status_call(show_program_status, {})
    budget_state = _safe_status_call(show_budget_state, {"budget_window_status": ""})
    program_handoff = _safe_status_call(show_program_handoff, {})
    next_task = select_next_task(policy)
    return {
        "state": state,
        "policy": policy,
        "runtime_session": runtime_session,
        "next_task_id": next_task["task_id"] if next_task else "",
        "last_wake_reason": str(runtime_session.get("last_wake_reason", "")),
        "session_end_reason": str(runtime_session.get("session_end_reason", "")),
        "idle_cycles": int(runtime_session.get("idle_cycles", 0)),
        "queue_planner_enabled": bool(queue_plan.get("enabled", False)),
        "last_planner_run_at": str(queue_plan.get("state", {}).get("last_planner_run_at", "")),
        "last_generated_task_ids": list(queue_plan.get("state", {}).get("last_generated_task_ids", [])),
        "active_workflow_id": str((workflow_status.get("workflow") or {}).get("workflow_id", "")),
        "current_workflow_stage": str((workflow_status.get("workflow") or {}).get("current_stage", "")),
        "workflow_status": str((workflow_status.get("workflow") or {}).get("status", "")),
        "program_goal": str(program_state.get("primary_goal", "")),
        "program_status": str(program_state.get("status", "")),
        "active_milestone": str(program_state.get("active_milestone", "")),
        "program_block_reason": str(program_state.get("program_block_reason", "")),
        "budget_window_status": str(budget_state.get("budget_window_status", "")),
        "resume_after_budget_reset": bool(program_state.get("resume_after_budget_reset", False)),
        "next_recommended_workflow": str(program_handoff.get("next_recommended_workflow", "")),
        "next_ready_task_id": str(program_handoff.get("next_ready_task_id", "")),
        "next_ready_task_template": str(program_handoff.get("next_ready_task_template", "")),
        "program_stop_reason": str(program_handoff.get("program_stop_reason", "")),
    }


def _resume_from_checkpoint(actual_runner_id: str, state: dict[str, Any]) -> dict[str, Any]:
    run_id = str(state.get("current_run_id", ""))
    run_dir = _run_dir(run_id)
    checkpoint = load_stage_checkpoint(run_dir)
    if not checkpoint:
        return {
            "runner_id": actual_runner_id,
            "run_id": run_id,
            "recovered_stage": "",
            "resume_action": "no_checkpoint",
            "artifacts_verified": {},
        }

    task_id = str(checkpoint.get("task_id", "") or state.get("active_task_id", ""))
    stage = str(checkpoint.get("stage", ""))
    artifacts_ready = dict(checkpoint.get("artifacts_ready", {}))
    decision_path = run_dir / PLANNER_DECISION_NAME
    execution_path = run_dir / EXECUTION_RESULT_NAME
    verdict_path = run_dir / REVIEW_VERDICT_NAME

    if stage in ("planner_decision_written", "execution_started") and decision_path.exists():
        decision = validate_planner_decision(load_json(decision_path)).data
        state.update(
            {
                "current_run_id": run_id,
                "active_task_id": task_id,
                "status": "planner_workspace_ready",
                "current_workspace_role": "",
                "current_workspace_path": "",
                "awaiting_output_file": "",
            }
        )
        _write_state(state)
        if str(decision.get("workflow_kind")) == "implementation_task":
            prepare_implementation_workspace(str(decision_path))
        else:
            prepare_executor_workspace(str(decision_path))
        execution_path = run_execution(str(decision_path))
        _heartbeat(actual_runner_id)
        prepare_reviewer_workspace(str(execution_path))
        verdict_template_path = prepare_review_verdict_template(str(execution_path))
        verdict_path = _write_review_verdict_from_template(verdict_template_path)
        summary_path = advance_review(str(verdict_path))
        return {
            "runner_id": actual_runner_id,
            "run_id": run_id,
            "recovered_stage": stage,
            "resume_action": "rerun_execution_from_boundary",
            "artifacts_verified": {
                **artifacts_ready,
                "execution_result": execution_path.exists(),
                "review_verdict": verdict_path.exists(),
            },
            "summary_path": str(summary_path),
            "status": str(_load_state().get("status", "")),
        }

    if stage == "execution_finished" and execution_path.exists():
        state.update(
            {
                "current_run_id": run_id,
                "active_task_id": task_id,
                "status": "executed",
                "current_workspace_role": "",
                "current_workspace_path": "",
                "awaiting_output_file": "",
            }
        )
        _write_state(state)
        prepare_reviewer_workspace(str(execution_path))
        verdict_template_path = prepare_review_verdict_template(str(execution_path))
        verdict_path = _write_review_verdict_from_template(verdict_template_path)
        summary_path = advance_review(str(verdict_path))
        return {
            "runner_id": actual_runner_id,
            "run_id": run_id,
            "recovered_stage": stage,
            "resume_action": "resume_from_reviewer_stage",
            "artifacts_verified": {
                **artifacts_ready,
                "execution_result": True,
                "review_verdict": verdict_path.exists(),
            },
            "summary_path": str(summary_path),
            "status": str(_load_state().get("status", "")),
        }

    if stage == "review_finished" and verdict_path.exists():
        state.update(
            {
                "current_run_id": run_id,
                "active_task_id": task_id,
                "status": "reviewer_workspace_ready",
                "current_workspace_role": "",
                "current_workspace_path": "",
                "awaiting_output_file": "",
            }
        )
        _write_state(state)
        summary_path = advance_review(str(verdict_path))
        return {
            "runner_id": actual_runner_id,
            "run_id": run_id,
            "recovered_stage": stage,
            "resume_action": "commit_state_from_review",
            "artifacts_verified": {
                **artifacts_ready,
                "review_verdict": True,
            },
            "summary_path": str(summary_path),
            "status": str(_load_state().get("status", "")),
        }

    return {
        "runner_id": actual_runner_id,
        "run_id": run_id,
        "recovered_stage": stage,
        "resume_action": "checkpoint_artifacts_missing",
        "artifacts_verified": artifacts_ready,
    }


def resume_stale(runner_id: str | None = None) -> dict[str, Any]:
    policy = get_runtime_policy()
    actual_runner_id = runner_id or _new_runner_id()
    state = _acquire_lease(actual_runner_id, policy, allow_stale_takeover=True)
    state["active_lease_status"] = "resumed"
    _write_state(state)
    result = _resume_from_checkpoint(actual_runner_id, state)
    append_event(
        "stale_resumed",
        runner_id=actual_runner_id,
        task_id=str(state.get("active_task_id", "")),
        run_id=str(state.get("current_run_id", "")),
        state_status=str(_load_state().get("status", "")),
        reason_code="stale_resumed",
        details=_event_recovery_fields(result),
    )
    result["active_lease_status"] = "resumed"
    _release_lease(actual_runner_id)
    return result


def _find_gated_ready_task(policy: dict[str, Any]) -> dict[str, Any] | None:
    now_iso = _now_iso()
    current_sprint_text = _read_current_sprint_text()
    allowed = set(get_allowed_unattended_workflows(policy))
    candidates: list[dict[str, Any]] = []
    for task_record in list_task_records():
        if str(task_record.get("status")) != "ready":
            continue
        if not bool(task_record.get("autopilot_enabled", True)):
            continue
        if is_task_in_cooldown(task_record, now_iso=now_iso):
            continue
        workflow_kind = str(task_record.get("workflow_kind"))
        if workflow_kind == "implementation_task":
            if not _implementation_autopilot_allowed(task_record, policy):
                candidates.append(task_record)
        elif workflow_kind == "experiment_run":
            if not _experiment_autopilot_allowed(task_record, policy):
                candidates.append(task_record)
        elif workflow_kind not in allowed:
            candidates.append(task_record)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: task_priority_key(item, current_sprint_text))[0]


def run_once(runner_id: str | None = None) -> dict[str, Any]:
    policy = get_runtime_policy()
    actual_runner_id = runner_id or _new_runner_id()
    round_started = perf_counter()
    state = _acquire_lease(actual_runner_id, policy, allow_stale_takeover=False)
    append_event(
        "runner_started",
        runner_id=actual_runner_id,
        task_id=str(state.get("active_task_id", "")),
        run_id=str(state.get("current_run_id", "")),
        state_status=str(state.get("status", "")),
    )
    try:
        task_record = select_next_task(policy)
        if task_record is None:
            if bool(policy.get("enable_workflow_engine", True)):
                ensure_program_progress()
            if bool(policy.get("enable_queue_planner", False)):
                plan_queue(max_generated_tasks=1)
                task_record = select_next_task(policy)
        if task_record is None:
            gated = _find_gated_ready_task(policy)
            if gated is not None:
                _gate_task(gated, "autopilot_currently_gated", runner_id=actual_runner_id)
            _release_lease(actual_runner_id)
            return {"status": "idle", "runner_id": actual_runner_id, "reason": "no_eligible_task"}

        task_record = _increment_attempt(task_record)
        save_task_record(task_record)
        _pause_due_to_retry_limit(task_record, policy)
        task_record = get_task_record(task_record["task_id"])
        if str(task_record.get("status")) == "paused_for_human":
            _release_lease(actual_runner_id)
            return {"status": "paused_for_human", "task_id": task_record["task_id"], "runner_id": actual_runner_id}

        append_event(
            "task_selected",
            runner_id=actual_runner_id,
            task_id=task_record["task_id"],
            state_status=str(_load_state().get("status", "")),
            details={"workflow_kind": task_record["workflow_kind"]},
        )
        planner_started = perf_counter()
        packet_path = prepare_plan_packet(task_id=task_record["task_id"])
        run_id = packet_path.parent.name
        _checkpoint_stage(actual_runner_id, run_id, task_record["task_id"], "lease_acquired", str(_load_state().get("status", "")), "task_selection")
        _checkpoint_stage(actual_runner_id, run_id, task_record["task_id"], "task_selected", str(_load_state().get("status", "")), "planner")
        _heartbeat(actual_runner_id)
        prepare_planner_workspace(run_id)

        decision = _autoplan_decision(task_record, run_id, str(_load_state().get("phase", "")))
        decision_path = packet_path.parent / PLANNER_DECISION_NAME
        write_json(decision_path, decision)
        _checkpoint_stage(actual_runner_id, run_id, task_record["task_id"], "planner_decision_written", str(_load_state().get("status", "")), "execution")
        planner_ms = int((perf_counter() - planner_started) * 1000)
        append_event(
            "run_started",
            runner_id=actual_runner_id,
            task_id=task_record["task_id"],
            run_id=run_id,
            state_status=str(_load_state().get("status", "")),
            details={"workflow_kind": task_record["workflow_kind"]},
        )

        execution_started = perf_counter()
        if str(task_record.get("workflow_kind")) == "implementation_task":
            prepare_implementation_workspace(str(decision_path))
        elif str(task_record.get("workflow_kind")) == "experiment_run":
            prepare_experiment_workspace(str(decision_path))
        else:
            prepare_executor_workspace(str(decision_path))
        execution_path = run_execution(str(decision_path))
        if str(task_record.get("workflow_kind")) == "experiment_run":
            decision_payload = load_json(decision_path)
            run_dir_arg = str(decision_payload.get("action", {}).get("args", {}).get("run_dir", "")).strip()
            config_path = str(decision_payload.get("action", {}).get("args", {}).get("config_path", "")).strip()
            if run_dir_arg:
                experiment_record_path = sync_experiment_from_run(task_record["task_id"], run_dir_arg, status="candidate", config_path=config_path)
                experiment_record = load_json(experiment_record_path)
                decision_payload["linked_experiment_id"] = str(experiment_record.get("experiment_id", ""))
                write_json(decision_path, decision_payload)
        execution_ms = int((perf_counter() - execution_started) * 1000)
        _heartbeat(actual_runner_id)
        review_started = perf_counter()
        prepare_reviewer_workspace(str(execution_path))
        verdict_template_path = prepare_review_verdict_template(str(execution_path))
        verdict_path = _write_review_verdict_from_template(verdict_template_path)
        summary_path = advance_review(str(verdict_path))
        review_ms = int((perf_counter() - review_started) * 1000)
        current_state = _load_state()
        execution = load_json(execution_path)
        verdict = load_json(verdict_path)
        checks_ms = int(execution.get("artifacts", {}).get("checks_duration_ms", 0) or 0)
        round_ms = int((perf_counter() - round_started) * 1000)
        if not is_progress_meaningful(execution, verdict, current_state):
            pause_fields = _event_pause_fields(current_state)
            append_event(
                "no_progress_pause",
                runner_id=actual_runner_id,
                task_id=task_record["task_id"],
                run_id=run_id,
                state_status=str(current_state.get("status", "")),
                reason_code="two_rounds_no_progress" if str(current_state.get("status")) == "paused_for_human" else "",
                details={
                    "recommended_action_summary": pause_fields["suggested_next_actions"][0] if pause_fields["suggested_next_actions"] else "",
                    **pause_fields["details"],
                },
                suggested_next_actions=pause_fields["suggested_next_actions"],
            )
        if verdict.get("verdict") == "revise":
            issues = list(verdict.get("issues", []))
            pause_fields = _event_pause_fields(current_state)
            append_event(
                "review_failed",
                runner_id=actual_runner_id,
                task_id=task_record["task_id"],
                run_id=run_id,
                state_status=str(current_state.get("status", "")),
                reason_code=_canonical_reason_code(issues[0]) if issues else "review_failed",
                details={
                    "issues": issues,
                    "recommended_action_summary": pause_fields["suggested_next_actions"][0] if pause_fields["suggested_next_actions"] else "",
                    **pause_fields["details"],
                },
                suggested_next_actions=pause_fields["suggested_next_actions"],
            )
        pause_fields = _event_pause_fields(current_state)
        append_event(
            "run_completed",
            runner_id=actual_runner_id,
            task_id=task_record["task_id"],
            run_id=run_id,
            state_status=str(current_state.get("status", "")),
            reason_code=str(current_state.get("last_blocker_code", "")),
            details={
                "summary_path": str(summary_path),
                "planner_ms": planner_ms,
                "execution_ms": execution_ms,
                "checks_ms": checks_ms,
                "review_ms": review_ms,
                "round_ms": round_ms,
                "recommended_action_summary": pause_fields["suggested_next_actions"][0] if pause_fields["suggested_next_actions"] else "",
                **pause_fields["details"],
            },
            suggested_next_actions=pause_fields["suggested_next_actions"],
        )
        _release_lease(actual_runner_id)
        return {
            "status": str(current_state.get("status", "")),
            "runner_id": actual_runner_id,
            "task_id": task_record["task_id"],
            "run_id": run_id,
            "summary_path": str(summary_path),
        }
    except GovernorError:
        current_state = _load_state()
        pause_fields = _event_pause_fields(current_state)
        append_event(
            "run_paused",
            runner_id=actual_runner_id,
            task_id=str(current_state.get("active_task_id", "")),
            run_id=str(current_state.get("current_run_id", "")),
            state_status=str(current_state.get("status", "")),
            reason_code=str(current_state.get("blocked_reason_code", "") or current_state.get("last_blocker_code", "")),
            details={
                "recommended_action_summary": pause_fields["suggested_next_actions"][0] if pause_fields["suggested_next_actions"] else "",
                **pause_fields["details"],
            },
            suggested_next_actions=pause_fields["suggested_next_actions"],
        )
        _release_lease(actual_runner_id, status="paused")
        raise


def run_loop(
    runner_id: str | None = None,
    *,
    max_rounds: int | None = None,
    max_session_minutes: int | None = None,
    idle_sleep_seconds_override: int | None = None,
    max_idle_sleep_seconds_override: int | None = None,
) -> dict[str, Any]:
    policy = get_runtime_policy()
    actual_runner_id = runner_id or _new_runner_id()
    max_total = max_rounds if max_rounds is not None else int(policy.get("max_runner_session_rounds", policy.get("max_auto_rounds_total", 0)))
    session_minutes = max_session_minutes if max_session_minutes is not None else int(policy.get("max_runner_session_minutes", DEFAULT_INTERVENTION_POLICY["max_runner_session_minutes"]))
    idle_sleep_seconds = idle_sleep_seconds_override if idle_sleep_seconds_override is not None else int(policy.get("idle_sleep_seconds", DEFAULT_INTERVENTION_POLICY["idle_sleep_seconds"]))
    max_idle_sleep_seconds = max_idle_sleep_seconds_override if max_idle_sleep_seconds_override is not None else int(policy.get("max_idle_sleep_seconds", DEFAULT_INTERVENTION_POLICY["max_idle_sleep_seconds"]))
    backoff_multiplier = float(policy.get("backoff_multiplier", DEFAULT_INTERVENTION_POLICY["backoff_multiplier"]))
    start = _now()
    completed = 0
    last_result: dict[str, Any] = {"status": "idle", "runner_id": actual_runner_id}
    idle_cycles = 0
    current_sleep_seconds = max(1, idle_sleep_seconds)
    previous_signature = task_registry_signature()
    last_wake_reason = "initial_boot"
    session_end_reason = ""
    session = _session_snapshot(
        runner_id=actual_runner_id,
        started_at=start.isoformat(timespec="seconds"),
        last_heartbeat_at=start.isoformat(timespec="seconds"),
        last_wake_reason=last_wake_reason,
    )
    _write_runtime_session(session)
    append_event(
        "session_started",
        runner_id=actual_runner_id,
        state_status=str(_load_state().get("status", "")),
        details={"wake_reason": last_wake_reason},
    )
    append_event(
        "runner_woke",
        runner_id=actual_runner_id,
        state_status=str(_load_state().get("status", "")),
        details={"wake_reason": last_wake_reason},
    )
    while True:
        elapsed = _now() - start
        if session_minutes > 0 and elapsed > timedelta(minutes=session_minutes):
            session_end_reason = "max_session_minutes_reached"
            break
        if max_total > 0 and completed >= max_total:
            session_end_reason = "max_session_rounds_reached"
            break

        state = _load_state()
        now_iso = _now_iso()
        tasks = list_task_records()
        eligible_task = select_next_task(policy)
        cooldown_ready_ids = cooldown_ready_task_ids(tasks, now_iso=now_iso) if bool(policy.get("wake_on_cooldown_expiry", True)) else []
        stale_available = bool(policy.get("wake_on_stale_run", True)) and bool(str(state.get("runner_id", "")).strip()) and _is_stale(state, policy, now=_now())
        current_signature = task_registry_signature()
        registry_changed = bool(policy.get("wake_on_task_registry_change", True)) and current_signature != previous_signature
        previous_signature = current_signature
        planner_wake_reason = ""

        if eligible_task is None and bool(policy.get("enable_workflow_engine", True)):
            program_result = ensure_program_progress()
            if bool(program_result.get("budget_reset", False)):
                planner_wake_reason = "budget_window_reset"
                registry_changed = True
                current_signature = task_registry_signature()
                previous_signature = current_signature
            if bool(program_result.get("created_workflow", False)):
                planner_wake_reason = "workflow_stage_advanced"
                registry_changed = True
                current_signature = task_registry_signature()
                previous_signature = current_signature

        if eligible_task is None and bool(policy.get("enable_queue_planner", False)):
            planner_result = plan_queue()
            if planner_result.get("generated_task_ids"):
                eligible_task = select_next_task(policy)
                registry_changed = True
                current_signature = task_registry_signature()
                previous_signature = current_signature
                if str(planner_result.get("workflow_id", "")).strip():
                    planner_wake_reason = "workflow_stage_advanced"

        wake_reason = wake_reason_for_cycle(
            has_eligible_task=eligible_task is not None,
            stale_available=stale_available,
            cooldown_ready_ids=cooldown_ready_ids,
            registry_changed=registry_changed,
            initial_boot=False,
        )
        if planner_wake_reason:
            wake_reason = planner_wake_reason

        if stale_available:
            last_wake_reason = wake_reason or "stale_takeover"
            append_event(
                "runner_woke",
                runner_id=actual_runner_id,
                task_id=str(state.get("active_task_id", "")),
                run_id=str(state.get("current_run_id", "")),
                state_status=str(state.get("status", "")),
                details={"wake_reason": last_wake_reason},
            )
            last_result = resume_stale(actual_runner_id)
            completed += 1
            idle_cycles = 0
            current_sleep_seconds = max(1, idle_sleep_seconds)
        elif eligible_task is not None:
            if cooldown_ready_ids and str(eligible_task.get("task_id", "")) in cooldown_ready_ids:
                append_event(
                    "cooldown_expired",
                    runner_id=actual_runner_id,
                    task_id=str(eligible_task.get("task_id", "")),
                    state_status=str(_load_state().get("status", "")),
                    details={"wake_reason": "retry_after_cooldown"},
                )
            if registry_changed:
                append_event(
                    "task_registry_changed",
                    runner_id=actual_runner_id,
                    task_id=str(eligible_task.get("task_id", "")),
                    state_status=str(_load_state().get("status", "")),
                )
            last_wake_reason = wake_reason or "eligible_task_found"
            append_event(
                "runner_woke",
                runner_id=actual_runner_id,
                task_id=str(eligible_task.get("task_id", "")),
                state_status=str(_load_state().get("status", "")),
                details={"wake_reason": last_wake_reason},
            )
            last_result = run_once(actual_runner_id)
            completed += 1
            idle_cycles = 0
            current_sleep_seconds = max(1, idle_sleep_seconds)
        else:
            program_stop_reason = _program_waiting_stop_reason()
            if program_stop_reason:
                session_end_reason = program_stop_reason
                break
            idle_cycles += 1
            append_event(
                "runner_idle",
                runner_id=actual_runner_id,
                state_status=str(state.get("status", "")),
                details={"sleep_seconds": current_sleep_seconds, "idle_cycle": idle_cycles},
            )
            session = _session_snapshot(
                runner_id=actual_runner_id,
                started_at=session["started_at"],
                last_heartbeat_at=_now_iso(),
                rounds_completed=completed,
                idle_cycles=idle_cycles,
                last_wake_reason=last_wake_reason,
                session_end_reason="",
                last_run_id=str(last_result.get("run_id", "")),
                last_task_id=str(last_result.get("task_id", "")),
            )
            _write_runtime_session(session)
            time.sleep(current_sleep_seconds)
            current_sleep_seconds = min(max_idle_sleep_seconds, max(1, int(current_sleep_seconds * backoff_multiplier)))
            continue

        session = _session_snapshot(
            runner_id=actual_runner_id,
            started_at=session["started_at"],
            last_heartbeat_at=_now_iso(),
            rounds_completed=completed,
            idle_cycles=idle_cycles,
            last_wake_reason=last_wake_reason,
            session_end_reason="",
            last_run_id=str(last_result.get("run_id", "")),
            last_task_id=str(last_result.get("task_id", "")),
        )
        _write_runtime_session(session)
        if last_result.get("status") == "paused_for_human":
            session_end_reason = str(last_result.get("status", "paused_for_human"))
            break

    final_state = _load_state()
    final_session = _session_snapshot(
        runner_id=actual_runner_id,
        started_at=session["started_at"],
        last_heartbeat_at=_now_iso(),
        rounds_completed=completed,
        idle_cycles=idle_cycles,
        last_wake_reason=last_wake_reason,
        session_end_reason=session_end_reason or str(last_result.get("status", "")) or "session_stopped",
        last_run_id=str(last_result.get("run_id", "")),
        last_task_id=str(last_result.get("task_id", "")),
    )
    _write_runtime_session(final_session)
    pending_task = select_next_task(policy)
    _append_session_history(
        final_session,
        unresolved={
            "paused_for_human": final_state.get("status") == "paused_for_human",
            "stale_run_pending": bool(str(final_state.get("runner_id", "")).strip()) and _is_stale(final_state, policy, now=_now()),
            "next_task_id": pending_task["task_id"] if pending_task else "",
        },
    )
    append_event(
        "session_ended",
        runner_id=actual_runner_id,
        task_id=str(last_result.get("task_id", "")),
        run_id=str(last_result.get("run_id", "")),
        state_status=str(final_state.get("status", "")),
        details={
            "session_end_reason": final_session["session_end_reason"],
            "idle_cycles": idle_cycles,
            "last_wake_reason": last_wake_reason,
        },
    )
    return {
        "runner_id": actual_runner_id,
        "rounds_completed": completed,
        "last_result": last_result,
        "session_end_reason": final_session["session_end_reason"],
        "idle_cycles": idle_cycles,
        "last_wake_reason": last_wake_reason,
    }
