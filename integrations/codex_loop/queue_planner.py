from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import (
    DEFAULT_INTERVENTION_POLICY,
    QUEUE_PLANNER_STATE_PATH,
    TASK_REGISTRY_DIR,
)
from integrations.codex_loop.events import append_event
from integrations.codex_loop.governor import (
    create_task,
    get_runtime_policy,
    get_task_record,
    list_task_records,
    save_task_record,
)
from integrations.codex_loop.schemas import (
    default_queue_planner_state,
    ensure_runtime_state_files,
    load_json,
    SchemaValidationError,
    validate_queue_planner_state,
    write_json,
)
from integrations.codex_loop.task_templates import (
    build_gate_load_balance_template,
)
from integrations.codex_loop.workflow_registry import (
    active_workflow_instance,
    advance_workflow_stage,
    create_workflow_instance,
    load_program_state,
    save_program_state,
    workflow_stages,
)


STAGE_TO_TASK_ID = {
    "real_case_staging": "2026-04-01-gate-load-balance-real-case-staging",
    "real_case_closeout": "2026-04-01-gate-load-balance-real-case-closeout-decision",
    "higher_budget_staging": "2026-04-01-gate-load-balance-higher-budget-staging",
    "higher_budget_closeout": "2026-04-01-gate-load-balance-higher-budget-closeout-decision",
    "second_seed_higher_budget": "2026-04-01-gate-load-balance-second-seed-higher-budget",
    "second_seed_closeout": "2026-04-01-gate-load-balance-second-seed-closeout-decision",
    "promotion_readiness_review": "2026-04-01-gate-load-balance-promotion-readiness-review",
    "extended_real_case_staging": "2026-04-01-gate-load-balance-extended-real-case-staging",
    "extended_real_case_closeout": "2026-04-01-gate-load-balance-extended-real-case-closeout-decision",
    "promotion_candidate_decision": "2026-04-01-gate-load-balance-promotion-candidate-decision",
    "inference_protocol_evidence_closeout": "2026-04-01-multilabel-inference-protocol-evidence-closeout",
    "inference_protocol_decision": "2026-04-01-multilabel-inference-protocol-decision",
    "inference_protocol_handoff": "2026-04-01-multilabel-inference-protocol-handoff",
    "promotion_followup_closeout": "2026-04-01-gate-load-balance-promotion-followup-closeout",
    "promotion_followup_decision": "2026-04-01-gate-load-balance-promotion-followup-decision",
    "dual_output_plan_evidence_closeout": "2026-04-01-multilabel-dual-output-plan-evidence-closeout",
    "dual_output_plan_decision": "2026-04-01-multilabel-dual-output-plan-decision",
    "dual_output_plan_handoff": "2026-04-01-multilabel-dual-output-plan-handoff",
}

GENERATABLE_STAGES = {
    "promotion_readiness_review": "promotion_readiness_review",
    "extended_real_case_staging": "extended_real_case_staging",
    "extended_real_case_closeout": "extended_real_case_closeout",
    "promotion_candidate_decision": "promotion_candidate_decision",
    "inference_protocol_evidence_closeout": "inference_protocol_evidence_closeout",
    "inference_protocol_decision": "inference_protocol_decision",
    "inference_protocol_handoff": "inference_protocol_handoff",
    "promotion_followup_closeout": "promotion_followup_closeout",
    "promotion_followup_decision": "promotion_followup_decision",
    "dual_output_plan_evidence_closeout": "dual_output_plan_evidence_closeout",
    "dual_output_plan_decision": "dual_output_plan_decision",
    "dual_output_plan_handoff": "dual_output_plan_handoff",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load_planner_state() -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    try:
        return validate_queue_planner_state(load_json(QUEUE_PLANNER_STATE_PATH)).data
    except (json.JSONDecodeError, OSError, SchemaValidationError, ValueError, NameError):
        return validate_queue_planner_state(default_queue_planner_state()).data


def _write_planner_state(payload: dict[str, Any]) -> None:
    write_json(QUEUE_PLANNER_STATE_PATH, validate_queue_planner_state(payload).data)


def _task_exists(task_id: str) -> bool:
    return (TASK_REGISTRY_DIR / f"{task_id}.json").exists()


def _task_by_id(task_id: str) -> dict[str, Any] | None:
    if not task_id:
        return None
    path = TASK_REGISTRY_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    return load_json(path)


def _allow_template(policy: dict[str, Any], template_category: str) -> bool:
    allowed = {str(item) for item in policy.get("queue_planner_allowed_templates", [])}
    return template_category in allowed


def _materialize_candidate(candidate: dict[str, Any]) -> str:
    task_path = Path(candidate["task_path"])
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(candidate["markdown"], encoding="utf-8")
    record_path = create_task(str(task_path), **candidate["create_kwargs"])
    record = get_task_record(Path(record_path).stem)
    record.update(candidate["record_overrides"])
    record["updated_at"] = _now_iso()
    save_task_record(record)
    return str(record["task_id"])


def _workflow_signal_from_task(task_record: dict[str, Any]) -> dict[str, Any]:
    signal = task_record.get("workflow_signal", {})
    return dict(signal) if isinstance(signal, dict) else {}


def _task_completed(task_record: dict[str, Any] | None) -> bool:
    return bool(task_record) and str(task_record.get("status", "")) == "completed"


def _task_succeeded_for_stage(stage: str, task_record: dict[str, Any] | None) -> bool:
    if not task_record:
        return False
    status = str(task_record.get("status", ""))
    if stage in ("real_case_staging", "higher_budget_staging", "second_seed_higher_budget", "extended_real_case_staging"):
        return status in ("evaluating", "completed")
    if stage in ("real_case_closeout", "higher_budget_closeout", "second_seed_closeout", "promotion_readiness_review", "extended_real_case_closeout", "promotion_candidate_decision"):
        return status == "completed"
    if stage in ("inference_protocol_evidence_closeout", "inference_protocol_handoff", "promotion_followup_closeout"):
        return status == "completed"
    if stage in ("inference_protocol_decision", "promotion_followup_decision"):
        return status == "completed"
    if stage in ("dual_output_plan_evidence_closeout", "dual_output_plan_decision", "dual_output_plan_handoff"):
        return status == "completed"
    return False


def _workflow_can_advance(stage: str, task_record: dict[str, Any] | None) -> tuple[bool, str]:
    if not task_record:
        return False, "task_missing"
    if not _task_succeeded_for_stage(stage, task_record):
        status = str(task_record.get("status", ""))
        if status in ("paused_for_human", "blocked"):
            return False, f"task_blocked:{status}"
        return False, "task_incomplete"
    signal = _workflow_signal_from_task(task_record)
    if stage == "promotion_readiness_review" and not bool(signal.get("enter_extended_staging", False)):
        return False, "workflow_signal_missing_enter_extended_staging"
    if stage == "extended_real_case_closeout" and not bool(signal.get("enter_promotion_candidate", False)):
        return False, "workflow_signal_missing_enter_promotion_candidate"
    if bool(signal.get("runtime_blocker", False)):
        return False, "runtime_blocker"
    return True, ""


def _bootstrap_gate_load_balance_workflow() -> dict[str, Any]:
    existing = active_workflow_instance()
    if existing and str(existing.get("status", "")) == "active":
        return existing
    stages = workflow_stages("gate_load_balance_promotion")
    completed: list[str] = []
    current_stage = stages[0]
    blocked_stage = ""
    block_reason = ""
    for index, stage in enumerate(stages):
        task_id = STAGE_TO_TASK_ID.get(stage, "")
        task_record = _task_by_id(task_id)
        ok, reason = _workflow_can_advance(stage, task_record)
        if not ok and task_record and str(task_record.get("status", "")) == "completed":
            later_task_ids = [STAGE_TO_TASK_ID.get(item, "") for item in stages[index + 1 :]]
            if any(_task_by_id(item) for item in later_task_ids if item):
                ok = True
                reason = ""
        if ok:
            completed.append(stage)
            continue
        current_stage = stage
        if task_record and str(task_record.get("status", "")) in ("blocked", "paused_for_human"):
            blocked_stage = stage
            block_reason = reason or "task_blocked"
        break
    else:
        current_stage = ""
    if existing and str(existing.get("template_name", "")) == "gate_load_balance_promotion":
        instance = dict(existing)
    else:
        instance = create_workflow_instance(
            "gate_load_balance_promotion",
            workflow_id="gate-load-balance-promotion-main",
            lane="gate_load_balance",
            source_evidence_ids=completed,
            status="blocked" if block_reason else ("completed" if not current_stage else "active"),
        )
    instance["completed_stages"] = completed
    instance["current_stage"] = current_stage
    instance["blocked_stage"] = blocked_stage
    instance["block_reason"] = block_reason
    instance["status"] = "blocked" if block_reason else ("completed" if not current_stage else "active")
    instance["last_transition_at"] = _now_iso()
    from integrations.codex_loop.workflow_registry import save_workflow_instance

    saved = save_workflow_instance(instance)
    program = load_program_state()
    program["active_workflow_id"] = saved["workflow_id"]
    program["current_milestone"] = saved["current_stage"]
    program["completed_milestones"] = completed
    program["blocked_milestones"] = [blocked_stage] if blocked_stage else []
    program["last_program_summary"] = f"{saved['template_name']}:{saved['status']}:{saved['current_stage']}"
    save_program_state(program)
    return saved


def _instantiate_stage(stage: str) -> dict[str, Any] | None:
    template_name = GENERATABLE_STAGES.get(stage)
    if not template_name:
        return None
    return build_gate_load_balance_template(template_name, source_evidence_ids=[stage])


def _workflow_candidate(policy: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not bool(policy.get("enable_workflow_engine", True)):
        return None, None
    workflow = active_workflow_instance() or _bootstrap_gate_load_balance_workflow()
    stage = str(workflow.get("current_stage", "")).strip()
    if not stage:
        return None, workflow
    while stage:
        task_id = STAGE_TO_TASK_ID.get(stage, "")
        existing = _task_by_id(task_id)
        ok, reason = _workflow_can_advance(stage, existing)
        if ok:
            next_stage = ""
            stages = workflow_stages(str(workflow["template_name"]))
            if stage in stages:
                idx = stages.index(stage)
                next_stage = stages[idx + 1] if idx + 1 < len(stages) else ""
            workflow = advance_workflow_stage(
                str(workflow["workflow_id"]),
                next_stage=next_stage,
                workflow_signal=_workflow_signal_from_task(existing),
            )
            stage = str(workflow.get("current_stage", "")).strip()
            continue
        if existing:
            if reason:
                advance_workflow_stage(
                    str(workflow["workflow_id"]),
                    next_stage=stage,
                    block_reason=reason,
                    workflow_signal=_workflow_signal_from_task(existing),
                )
                workflow = active_workflow_instance() or workflow
            return None, workflow
        break
    if not stage:
        return None, workflow
    candidate = _instantiate_stage(stage)
    return candidate, workflow


def plan_queue(*, max_generated_tasks: int | None = None) -> dict[str, Any]:
    policy = get_runtime_policy()
    state = _load_planner_state()
    state["last_planner_run_at"] = _now_iso()
    state["active_lane"] = str(policy.get("queue_planner_active_lane", ""))
    generated_task_ids: list[str] = []
    suppressed: list[str] = []
    if not bool(policy.get("enable_queue_planner", False)):
        state["last_generated_task_ids"] = []
        state["suppressed_candidates"] = []
        _write_planner_state(state)
        return {"enabled": False, "generated_task_ids": [], "suppressed_candidates": []}

    limit = max_generated_tasks if max_generated_tasks is not None else int(
        policy.get("queue_planner_max_generated_tasks", DEFAULT_INTERVENTION_POLICY["queue_planner_max_generated_tasks"])
    )
    candidate, workflow = _workflow_candidate(policy)
    if candidate and (limit <= 0 or len(generated_task_ids) < limit):
        template_name = str(candidate["record_overrides"]["template_name"])
        workflow_kind = str(candidate["create_kwargs"].get("workflow_kind", ""))
        if workflow_kind == "experiment_run":
            category = "experiment_run"
        elif workflow_kind == "results_closeout":
            category = "results_closeout"
        elif workflow_kind == "truth_calibration":
            category = "truth_calibration"
        else:
            category = template_name
        if _allow_template(policy, category):
            if _task_exists(candidate["task_id"]):
                suppressed.append(candidate["task_id"])
            else:
                task_id = _materialize_candidate(candidate)
                generated_task_ids.append(task_id)
                if workflow:
                    advance_workflow_stage(
                        str(workflow["workflow_id"]),
                        next_stage=str(workflow.get("current_stage", "")),
                        generated_task_id=task_id,
                        workflow_signal=dict(workflow.get("workflow_signal", {})),
                    )
                append_event(
                    "task_registry_changed",
                    task_id=task_id,
                    state_status="context_ready",
                    reason_code="workflow_stage_advanced",
                    details={
                        "generated_by": "workflow_engine",
                        "generation_reason": candidate["record_overrides"]["generation_reason"],
                        "template_name": candidate["record_overrides"]["template_name"],
                        "workflow_id": str((workflow or {}).get("workflow_id", "")),
                        "stage": str((workflow or {}).get("current_stage", "")),
                    },
                )

    state["last_generated_task_ids"] = generated_task_ids
    state["suppressed_candidates"] = suppressed
    history = list(state.get("generation_history", []))
    history.append(
        {
            "timestamp": state["last_planner_run_at"],
            "generated_task_ids": generated_task_ids,
            "reason": "workflow_queue_planner_run",
        }
    )
    state["generation_history"] = history[-20:]
    _write_planner_state(state)
    return {
        "enabled": True,
        "generated_task_ids": generated_task_ids,
        "suppressed_candidates": suppressed,
        "active_lane": state["active_lane"],
        "workflow_id": str((workflow or {}).get("workflow_id", "")),
        "current_stage": str((workflow or {}).get("current_stage", "")),
    }


def show_queue_plan() -> dict[str, Any]:
    policy = get_runtime_policy()
    state = _load_planner_state()
    workflow = active_workflow_instance() or _bootstrap_gate_load_balance_workflow()
    candidates: list[dict[str, Any]] = []
    if bool(policy.get("enable_queue_planner", False)):
        candidate, _ = _workflow_candidate(policy)
        if candidate:
            candidates.append(
                {
                    "task_id": candidate["task_id"],
                    "template_name": candidate["record_overrides"]["template_name"],
                    "generation_reason": candidate["record_overrides"]["generation_reason"],
                }
            )
    return {
        "state": state,
        "enabled": bool(policy.get("enable_queue_planner", False)),
        "workflow": workflow or {},
        "candidates": candidates,
    }
