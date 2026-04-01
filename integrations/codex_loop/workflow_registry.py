from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import (
    DEFAULT_INTERVENTION_POLICY,
    PROGRAM_STATE_PATH,
    WORKFLOW_STATE_DIR,
)
from integrations.codex_loop.schemas import (
    default_program_state,
    default_workflow_state,
    ensure_runtime_state_files,
    load_json,
    validate_program_state,
    validate_workflow_state,
    write_json,
)


WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "gate_load_balance_validation": {
        "lane": "gate_load_balance",
        "stages": [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
        ],
        "auto_instantiation": False,
    },
    "gate_load_balance_promotion": {
        "lane": "gate_load_balance",
        "stages": [
            "real_case_staging",
            "real_case_closeout",
            "higher_budget_staging",
            "higher_budget_closeout",
            "second_seed_higher_budget",
            "second_seed_closeout",
            "promotion_readiness_review",
            "extended_real_case_staging",
            "extended_real_case_closeout",
            "promotion_candidate_decision",
        ],
        "auto_instantiation": True,
    },
    "implementation_fix_then_retest": {
        "lane": "implementation",
        "stages": ["implementation_task", "experiment_run", "results_closeout"],
        "auto_instantiation": False,
    },
    "multilabel_inference_protocol_decision": {
        "lane": "gate_load_balance",
        "stages": ["inference_protocol_evidence_closeout", "inference_protocol_decision", "inference_protocol_handoff"],
        "auto_instantiation": True,
    },
    "promotion_candidate_followup": {
        "lane": "gate_load_balance",
        "stages": ["promotion_followup_closeout", "promotion_followup_decision"],
        "auto_instantiation": True,
    },
    "dual_output_implementation_plan": {
        "lane": "gate_load_balance",
        "stages": ["dual_output_plan_evidence_closeout", "dual_output_plan_decision", "dual_output_plan_handoff"],
        "auto_instantiation": True,
    },
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _workflow_path(workflow_id: str) -> Path:
    return WORKFLOW_STATE_DIR / f"{workflow_id}.json"


def load_program_state() -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    return validate_program_state(load_json(PROGRAM_STATE_PATH)).data


def save_program_state(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_program_state(payload).data
    write_json(PROGRAM_STATE_PATH, validated)
    return validated


def list_workflow_instances() -> list[dict[str, Any]]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    records: list[dict[str, Any]] = []
    for path in sorted(WORKFLOW_STATE_DIR.glob("*.json")):
        records.append(validate_workflow_state(load_json(path)).data)
    return records


def load_workflow_instance(workflow_id: str) -> dict[str, Any]:
    return validate_workflow_state(load_json(_workflow_path(workflow_id))).data


def save_workflow_instance(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_workflow_state(payload).data
    write_json(_workflow_path(validated["workflow_id"]), validated)
    return validated


def active_workflow_instance() -> dict[str, Any] | None:
    program = load_program_state()
    workflow_id = str(program.get("active_workflow_id", "")).strip()
    loaded_program_workflow: dict[str, Any] | None = None
    if workflow_id and _workflow_path(workflow_id).exists():
        loaded_program_workflow = load_workflow_instance(workflow_id)
        if str(loaded_program_workflow.get("status", "")) == "active":
            return loaded_program_workflow
    active_items = [item for item in list_workflow_instances() if str(item.get("status", "")) == "active"]
    if active_items:
        active_items.sort(key=lambda item: str(item.get("last_transition_at", "")))
        return active_items[-1]
    if loaded_program_workflow is not None:
        return loaded_program_workflow
    return None


def workflow_template(template_name: str) -> dict[str, Any]:
    return dict(WORKFLOW_TEMPLATES[template_name])


def workflow_stages(template_name: str) -> list[str]:
    return list(WORKFLOW_TEMPLATES[template_name]["stages"])


def create_workflow_instance(
    template_name: str,
    *,
    workflow_id: str | None = None,
    lane: str | None = None,
    source_evidence_ids: list[str] | None = None,
    status: str = "active",
) -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    template = workflow_template(template_name)
    resolved_id = workflow_id or f"{template_name}-{_now_iso().replace(':', '-').replace('+', '_')}"
    stages = workflow_stages(template_name)
    payload = default_workflow_state()
    payload.update(
        {
            "workflow_id": resolved_id,
            "template_name": template_name,
            "lane": lane or str(template.get("lane", "")),
            "status": status,
            "current_stage": stages[0] if stages else "",
            "completed_stages": [],
            "blocked_stage": "",
            "block_reason": "",
            "generated_task_ids": [],
            "source_evidence_ids": list(source_evidence_ids or []),
            "last_transition_at": _now_iso(),
            "workflow_signal": {},
        }
    )
    saved = save_workflow_instance(payload)
    program = load_program_state()
    program["active_lane"] = saved["lane"]
    program["active_workflow_id"] = saved["workflow_id"]
    program["primary_goal"] = "multilabel_gate_load_balance_promotion" if template_name == "gate_load_balance_promotion" else program.get("primary_goal", "")
    program["current_milestone"] = saved["current_stage"]
    save_program_state(program)
    return saved


def advance_workflow_stage(
    workflow_id: str,
    *,
    next_stage: str | None = None,
    block_reason: str = "",
    generated_task_id: str = "",
    workflow_signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_workflow_instance(workflow_id)
    stages = workflow_stages(str(state["template_name"]))
    current_stage = str(state.get("current_stage", ""))
    completed = list(state.get("completed_stages", []))
    if current_stage and current_stage not in completed:
        completed.append(current_stage)
    resolved_next = next_stage or ""
    if not resolved_next and current_stage in stages:
        idx = stages.index(current_stage)
        resolved_next = stages[idx + 1] if idx + 1 < len(stages) else ""
    state["completed_stages"] = completed
    state["current_stage"] = resolved_next
    state["blocked_stage"] = current_stage if block_reason else ""
    state["block_reason"] = block_reason
    if generated_task_id:
        generated = list(state.get("generated_task_ids", []))
        if generated_task_id not in generated:
            generated.append(generated_task_id)
        state["generated_task_ids"] = generated
    if workflow_signal is not None:
        state["workflow_signal"] = dict(workflow_signal)
    state["status"] = "blocked" if block_reason else ("completed" if not resolved_next else "active")
    state["last_transition_at"] = _now_iso()
    saved = save_workflow_instance(state)
    program = load_program_state()
    program["active_workflow_id"] = saved["workflow_id"]
    program["current_milestone"] = saved["current_stage"]
    completed_milestones = list(program.get("completed_milestones", []))
    for item in completed:
        if item and item not in completed_milestones:
            completed_milestones.append(item)
    program["completed_milestones"] = completed_milestones
    if block_reason and current_stage:
        blocked = list(program.get("blocked_milestones", []))
        if current_stage not in blocked:
            blocked.append(current_stage)
        program["blocked_milestones"] = blocked
    elif current_stage:
        program["blocked_milestones"] = [item for item in program.get("blocked_milestones", []) if item != current_stage]
    else:
        program["blocked_milestones"] = []
    program["last_program_summary"] = f"{saved['template_name']}:{saved['status']}:{saved['current_stage']}"
    save_program_state(program)
    return saved


def show_workflow_status(workflow_id: str | None = None) -> dict[str, Any]:
    workflow = load_workflow_instance(workflow_id) if workflow_id else active_workflow_instance()
    program = load_program_state()
    return {
        "program": program,
        "workflow": workflow or {},
        "templates": {name: {"lane": value["lane"], "stages": list(value["stages"])} for name, value in WORKFLOW_TEMPLATES.items()},
    }
