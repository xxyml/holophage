from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import (
    ACTIVE_OBJECTIVE_PATH,
    ALLOWED_ACTION_KINDS,
    ALLOWED_CHECKPOINT_STAGES,
    ALLOWED_CLOSEOUT_STATUSES,
    ALLOWED_EXPERIMENT_STATUSES,
    ALLOWED_RECOMMENDED_NEXT_MODES,
    ALLOWED_REVIEW_VERDICTS,
    ALLOWED_RISK_LEVELS,
    ALLOWED_STATES,
    ALLOWED_TASK_STATUSES,
    ALLOWED_TASK_TYPES,
    ALLOWED_WORKFLOW_STATUSES,
    ALLOWED_WORKFLOW_TEMPLATES,
    ALLOWED_WORKFLOW_KINDS,
    ALLOWED_WORKSPACE_KINDS,
    ALLOWED_WORKSPACE_ROLES,
    CURRENT_STATE_PATH,
    EVENTS_PATH,
    EXPERIMENT_INDEX_PATH,
    EXPERIMENT_REGISTRY_DIR,
    INTERVENTION_POLICY_PATH,
    LOOP_RUNS_DIR,
    LOOP_STATE_DIR,
    MILESTONES_PATH,
    DECISION_MEMORY_PATH,
    PROGRAM_BUDGET_STATE_PATH,
    BEST_KNOWN_METRICS_PATH,
    PROGRAM_HANDOFF_PATH,
    PROGRAM_STATE_PATH,
    QUEUE_PLANNER_STATE_PATH,
    RUNTIME_SESSION_HISTORY_PATH,
    RUNTIME_SESSION_PATH,
    TASK_INDEX_PATH,
    TASK_REGISTRY_DIR,
    WORKFLOW_STATE_DIR,
)


class SchemaValidationError(ValueError):
    """Raised when a loop document does not match the expected schema."""


@dataclass(frozen=True)
class ValidationResult:
    data: dict[str, Any]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"JSON root must be an object: {path}")
    return payload


def _merged(data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    merged.update(data)
    return merged


def _require_mapping(data: dict[str, Any], field: str) -> dict[str, Any]:
    value = data.get(field)
    if not isinstance(value, dict):
        raise SchemaValidationError(f"`{field}` must be an object.")
    return value


def _require_bool(data: dict[str, Any], field: str) -> bool:
    value = data.get(field)
    if not isinstance(value, bool):
        raise SchemaValidationError(f"`{field}` must be a boolean.")
    return value


def _require_string(data: dict[str, Any], field: str, allow_empty: bool = False) -> str:
    value = data.get(field)
    if not isinstance(value, str):
        raise SchemaValidationError(f"`{field}` must be a string.")
    if not allow_empty and not value.strip():
        raise SchemaValidationError(f"`{field}` must be a non-empty string.")
    return value


def _require_string_list(data: dict[str, Any], field: str, allow_empty: bool = False) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaValidationError(f"`{field}` must be a string list.")
    if not allow_empty and not [item for item in value if item.strip()]:
        raise SchemaValidationError(f"`{field}` must be a non-empty string list.")
    return value


def _require_optional_string(data: dict[str, Any], field: str) -> str:
    return _require_string(data, field, allow_empty=True)


def _normalize_decision_payload(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise SchemaValidationError("`decision_payload` must be an object.")
    normalized = {
        "topic": str(value.get("topic", "")),
        "chosen_protocol": str(value.get("chosen_protocol", "")),
        "rejected_protocols": list(value.get("rejected_protocols", [])),
        "requires_selector_experiment": value.get("requires_selector_experiment", None),
        "ready_for_implementation": value.get("ready_for_implementation", None),
        "implementation_scope": str(value.get("implementation_scope", "")),
        "requires_runtime_api_change": value.get("requires_runtime_api_change", None),
        "requires_model_output_change": value.get("requires_model_output_change", None),
        "next_action_hint": str(value.get("next_action_hint", "")),
    }
    if not isinstance(normalized["rejected_protocols"], list) or not all(
        isinstance(item, str) for item in normalized["rejected_protocols"]
    ):
        raise SchemaValidationError("`decision_payload.rejected_protocols` must be a string list.")
    for field in (
        "requires_selector_experiment",
        "ready_for_implementation",
        "requires_runtime_api_change",
        "requires_model_output_change",
    ):
        field_value = normalized[field]
        if field_value is not None and not isinstance(field_value, bool):
            raise SchemaValidationError(f"`decision_payload.{field}` must be a boolean when present.")
    return normalized


def default_current_state() -> dict[str, Any]:
    return {
        "loop_id": "holophage-main-loop",
        "status": "idle",
        "current_run_id": "",
        "active_task_file": "",
        "last_handoff_file": "",
        "phase": "",
        "round_count": 0,
        "consecutive_no_progress": 0,
        "current_workspace_role": "",
        "current_workspace_path": "",
        "last_completed_role": "",
        "awaiting_output_file": "",
        "last_transition_at": "",
        "active_task_id": "",
        "active_experiment_id": "",
        "auto_rounds_since_human": 0,
        "last_progress_fingerprint": "",
        "last_blocker_code": "",
        "runner_id": "",
        "lease_acquired_at": "",
        "heartbeat_at": "",
        "stale_after_seconds": 1800,
        "active_lease_status": "",
        "blocked_reason_code": "",
        "blocked_reason_detail": "",
        "suggested_next_actions": [],
    }


def default_active_objective() -> dict[str, Any]:
    return {
        "objective": "",
        "task_type": "",
        "owner": "planner",
        "success_definition": [],
    }


def default_runtime_session() -> dict[str, Any]:
    return {
        "runner_id": "",
        "started_at": "",
        "last_heartbeat_at": "",
        "rounds_completed": 0,
        "idle_cycles": 0,
        "last_wake_reason": "",
        "session_end_reason": "",
        "last_run_id": "",
        "last_task_id": "",
    }


def default_queue_planner_state() -> dict[str, Any]:
    return {
        "planner_version": 1,
        "active_lane": "",
        "last_planner_run_at": "",
        "last_generated_task_ids": [],
        "generation_history": [],
        "suppressed_candidates": [],
    }


def default_program_state() -> dict[str, Any]:
    return {
        "program_id": "holophage-program",
        "primary_goal": "multilabel_gate_load_balance_promotion",
        "active_lane": "gate_load_balance",
        "active_workflow_id": "",
        "status": "active",
        "current_milestone": "",
        "active_milestone": "",
        "completed_milestones": [],
        "blocked_milestones": [],
        "next_candidate_workflows": [],
        "last_program_summary": "",
        "next_workflow_template": "",
        "next_recommended_workflow": "",
        "program_block_reason": "",
        "decision_memory_summary": [],
        "resume_after_budget_reset": False,
    }


def default_workflow_state() -> dict[str, Any]:
    return {
        "workflow_id": "",
        "template_name": "",
        "lane": "",
        "status": "proposed",
        "current_stage": "",
        "completed_stages": [],
        "blocked_stage": "",
        "block_reason": "",
        "generated_task_ids": [],
        "source_evidence_ids": [],
        "last_transition_at": "",
        "workflow_signal": {},
    }


def default_milestones_state() -> dict[str, Any]:
    return {
        "program_id": "holophage-program",
        "milestones": [],
    }


def default_program_budget_state() -> dict[str, Any]:
    return {
        "date": "",
        "experiments_run_today": 0,
        "gpu_budget_minutes_used": 0,
        "last_reset_at": "",
        "budget_window_status": "open",
    }


def default_best_known_metrics() -> dict[str, Any]:
    return {
        "lane": "gate_load_balance",
        "best_val_l3_macro_f1": None,
        "best_val_multilabel_micro_f1": None,
        "best_test_multilabel_micro_f1": None,
        "best_gate_health_status": "",
        "best_mean_gates": {},
        "source_experiment_id": "",
        "last_updated_at": "",
    }


def default_program_handoff() -> dict[str, Any]:
    return {
        "program_id": "holophage-program",
        "primary_goal": "multilabel_gate_load_balance_promotion",
        "active_lane": "gate_load_balance",
        "active_milestone": "",
        "completed_milestones": [],
        "block_reason": "",
        "next_recommended_workflow": "",
        "next_ready_task_id": "",
        "next_ready_task_template": "",
        "program_stop_reason": "",
        "top_decisions": [],
        "best_known_metrics_snapshot": {},
        "updated_at": "",
    }


def default_task_index() -> dict[str, Any]:
    return {"tasks": []}


def default_experiment_index() -> dict[str, Any]:
    return {"experiments": []}


def validate_planner_decision(data: dict[str, Any]) -> ValidationResult:
    _require_string(data, "run_id")
    _require_string(data, "task_id")
    _require_string(data, "phase")
    workflow_kind = _require_string(data, "workflow_kind")
    if workflow_kind not in ALLOWED_WORKFLOW_KINDS:
        raise SchemaValidationError(f"`workflow_kind` must be one of {ALLOWED_WORKFLOW_KINDS}.")
    task_type = _require_string(data, "task_type", allow_empty=(workflow_kind in ("implementation_task", "experiment_run")))
    if task_type and task_type not in ALLOWED_TASK_TYPES:
        raise SchemaValidationError(f"`task_type` must be one of {ALLOWED_TASK_TYPES}.")
    _require_string(data, "objective")
    _require_bool(data, "preflight_required")
    _require_string_list(data, "success_criteria")
    _require_string_list(data, "fail_fast_conditions")
    _require_string_list(data, "review_focus")
    risk_level = _require_string(data, "risk_level")
    if risk_level not in ALLOWED_RISK_LEVELS:
        raise SchemaValidationError(f"`risk_level` must be one of {ALLOWED_RISK_LEVELS}.")
    _require_bool(data, "needs_human_before_execute")
    _require_bool(data, "autocontinue_eligible")
    _require_optional_string(data, "linked_experiment_id")
    _require_string_list(data, "allowed_write_paths", allow_empty=True)
    _require_string_list(data, "required_checks", allow_empty=True)

    action = _require_mapping(data, "action")
    kind = _require_string(action, "kind")
    if kind not in ALLOWED_ACTION_KINDS:
        raise SchemaValidationError(f"`action.kind` must be one of {ALLOWED_ACTION_KINDS}.")
    _require_string(action, "name")
    if not isinstance(action.get("args"), dict):
        raise SchemaValidationError("`action.args` must be an object.")
    return ValidationResult(data=data)


def validate_execution_result(data: dict[str, Any]) -> ValidationResult:
    merged = {
        "transcript_path": "",
        "step_count": 0,
        "failed_step": "",
        "decision_payload": {},
        **data,
    }
    _require_string(merged, "run_id")
    _require_string(merged, "task_id")
    _require_optional_string(merged, "linked_experiment_id")
    preflight = _require_mapping(merged, "preflight")
    _require_string(preflight, "skill")
    if not isinstance(preflight.get("exit_code"), int):
        raise SchemaValidationError("`preflight.exit_code` must be an integer.")
    _require_string(preflight, "status")

    action = _require_mapping(merged, "action")
    _require_string(action, "kind")
    _require_string(action, "name")
    _require_string(action, "command")
    if not isinstance(action.get("args"), dict):
        raise SchemaValidationError("`action.args` must be an object.")
    if not isinstance(action.get("exit_code"), int):
        raise SchemaValidationError("`action.exit_code` must be an integer.")
    stdout_json = action.get("stdout_json")
    if stdout_json is not None and not isinstance(stdout_json, dict):
        raise SchemaValidationError("`action.stdout_json` must be an object or null.")
    for field in ("stdout_excerpt", "stderr_excerpt"):
        if not isinstance(action.get(field), str):
            raise SchemaValidationError(f"`action.{field}` must be a string.")

    if not isinstance(merged.get("artifacts"), dict):
        raise SchemaValidationError("`artifacts` must be an object.")
    machine = _require_mapping(merged, "machine_assessment")
    _require_bool(machine, "fail_fast")
    _require_bool(machine, "completed_execution")
    detected_conditions = machine.get("detected_conditions")
    if not isinstance(detected_conditions, list) or not all(isinstance(item, str) for item in detected_conditions):
        raise SchemaValidationError("`machine_assessment.detected_conditions` must be a string list.")
    _require_string_list(merged, "write_set", allow_empty=True)
    _require_string_list(merged, "checks_run", allow_empty=True)
    _require_string_list(merged, "checks_passed", allow_empty=True)
    _require_optional_string(merged, "transcript_path")
    _require_optional_string(merged, "failed_step")
    if not isinstance(merged.get("step_count"), int) or int(merged["step_count"]) < 0:
        raise SchemaValidationError("`step_count` must be a non-negative integer.")
    merged["decision_payload"] = _normalize_decision_payload(merged.get("decision_payload", {}))
    progress_delta = _require_mapping(merged, "progress_delta")
    _require_string(progress_delta, "summary")
    _require_optional_string(progress_delta, "fingerprint")
    return ValidationResult(data=merged)


def validate_review_verdict(data: dict[str, Any]) -> ValidationResult:
    merged = {
        "workflow_signal": {},
        "decision_payload": {},
        **data,
    }
    _require_string(merged, "run_id")
    _require_string(merged, "task_id")
    _require_optional_string(merged, "linked_experiment_id")
    verdict = _require_string(merged, "verdict")
    if verdict not in ALLOWED_REVIEW_VERDICTS:
        raise SchemaValidationError(f"`verdict` must be one of {ALLOWED_REVIEW_VERDICTS}.")
    _require_bool(merged, "objective_met")
    _require_bool(merged, "needs_human")
    _require_bool(merged, "drift_detected")
    issues = merged.get("issues")
    if not isinstance(issues, list) or not all(isinstance(item, str) for item in issues):
        raise SchemaValidationError("`issues` must be a string list.")
    next_mode = _require_string(merged, "recommended_next_mode")
    if next_mode not in ALLOWED_RECOMMENDED_NEXT_MODES:
        raise SchemaValidationError(
            f"`recommended_next_mode` must be one of {ALLOWED_RECOMMENDED_NEXT_MODES}."
        )
    _require_string(merged, "next_objective")
    evidence = _require_mapping(merged, "evidence")
    for field in ("write_set", "checks_run", "checks_passed", "detected_conditions"):
        value = evidence.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise SchemaValidationError(f"`evidence.{field}` must be a string list.")
    workflow_signal = merged.get("workflow_signal", {})
    if not isinstance(workflow_signal, dict):
        raise SchemaValidationError("`workflow_signal` must be an object.")
    for field in (
        "enter_extended_staging",
        "enter_promotion_candidate",
        "runtime_blocker",
        "additional_seed_required",
    ):
        value = workflow_signal.get(field)
        if value is not None and not isinstance(value, bool):
            raise SchemaValidationError(f"`workflow_signal.{field}` must be a boolean when present.")
    merged["decision_payload"] = _normalize_decision_payload(merged.get("decision_payload", {}))
    return ValidationResult(data=merged)


def validate_current_state(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_current_state())
    _require_string(merged, "loop_id")
    status = _require_string(merged, "status")
    if status not in ALLOWED_STATES:
        raise SchemaValidationError(f"`status` must be one of {ALLOWED_STATES}.")
    for field in (
        "current_run_id",
        "active_task_file",
        "last_handoff_file",
        "phase",
        "current_workspace_role",
        "current_workspace_path",
        "last_completed_role",
        "awaiting_output_file",
        "last_transition_at",
        "active_task_id",
        "active_experiment_id",
        "last_progress_fingerprint",
        "last_blocker_code",
        "runner_id",
        "lease_acquired_at",
        "heartbeat_at",
        "active_lease_status",
        "blocked_reason_code",
        "blocked_reason_detail",
    ):
        if not isinstance(merged.get(field), str):
            raise SchemaValidationError(f"`{field}` must be a string.")
    suggested_next_actions = merged.get("suggested_next_actions", [])
    if not isinstance(suggested_next_actions, list) or not all(isinstance(item, str) for item in suggested_next_actions):
        raise SchemaValidationError("`suggested_next_actions` must be a string list.")
    current_workspace_role = merged.get("current_workspace_role", "")
    if current_workspace_role and current_workspace_role not in ALLOWED_WORKSPACE_ROLES:
        raise SchemaValidationError(f"`current_workspace_role` must be one of {ALLOWED_WORKSPACE_ROLES} when present.")
    last_completed_role = merged.get("last_completed_role", "")
    if last_completed_role and last_completed_role not in ALLOWED_WORKSPACE_ROLES:
        raise SchemaValidationError(f"`last_completed_role` must be one of {ALLOWED_WORKSPACE_ROLES} when present.")
    for field in ("round_count", "consecutive_no_progress", "auto_rounds_since_human", "stale_after_seconds"):
        if not isinstance(merged.get(field), int) or merged[field] < 0:
            raise SchemaValidationError(f"`{field}` must be a non-negative integer.")
    return ValidationResult(data=merged)


def validate_active_objective(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_active_objective())
    for field in ("objective", "task_type", "owner"):
        if not isinstance(merged.get(field), str):
            raise SchemaValidationError(f"`{field}` must be a string.")
    success_definition = merged.get("success_definition")
    if not isinstance(success_definition, list) or not all(isinstance(item, str) for item in success_definition):
        raise SchemaValidationError("`success_definition` must be a string list.")
    return ValidationResult(data=merged)


def validate_intervention_policy(data: dict[str, Any]) -> ValidationResult:
    merged = {
        "hard_stop": [],
        "soft_stop": [],
        "max_auto_rounds_per_task": 0,
        "max_auto_rounds_total": 0,
        "max_consecutive_no_progress": 0,
        "max_run_wall_clock_minutes": 0,
        "stale_after_seconds": 0,
        "max_retries_per_task": 0,
        "allowed_unattended_workflow_kinds": [],
        "default_unattended_risk_level": "",
        "pause_on_review_revise": False,
        "night_mode_low_risk_only": False,
        "allow_unattended_implementation": False,
        "implementation_max_files_touched": 0,
        "implementation_max_diff_lines": 0,
        "implementation_require_all_checks_pass": False,
        "implementation_pause_on_partial_write": False,
        "implementation_allowed_command_prefixes": [],
        "implementation_forbidden_command_prefixes": [],
        "implementation_forbidden_command_substrings": [],
        "implementation_require_pwsh_for_checks": False,
        "allow_unattended_experiment": False,
        "experiment_allowed_command_prefixes": [],
        "experiment_forbidden_command_prefixes": [],
        "experiment_forbidden_command_substrings": [],
        "experiment_max_wall_clock_minutes": 0,
        "experiment_require_summary_json": False,
        "experiment_require_metrics": False,
        "experiment_required_artifacts": [],
        "experiment_pause_on_missing_artifacts": False,
        "idle_sleep_seconds": 0,
        "backoff_multiplier": 1.0,
        "max_idle_sleep_seconds": 0,
        "wake_on_stale_run": False,
        "wake_on_cooldown_expiry": False,
        "wake_on_task_registry_change": False,
        "max_runner_session_minutes": 0,
        "max_runner_session_rounds": 0,
        "enable_queue_planner": False,
        "queue_planner_max_generated_tasks": 0,
        "queue_planner_allowed_templates": [],
        "queue_planner_max_budget_level": "",
        "queue_planner_require_closeout_pass": False,
        "queue_planner_allow_auxiliary_tasks": False,
        "queue_planner_active_lane": "",
        "enable_workflow_engine": False,
        "program_max_active_workflows": 0,
        "program_max_failed_workflows_per_lane": 0,
        "program_max_experiments_per_day": 0,
        "program_gpu_budget_minutes_per_day": 0,
        "program_pause_on_budget_exhausted": False,
        **data,
    }
    for field in ("hard_stop", "soft_stop"):
        values = merged.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise SchemaValidationError(f"`{field}` must be a string list.")
    for field in (
        "max_auto_rounds_per_task",
        "max_auto_rounds_total",
        "max_consecutive_no_progress",
        "max_run_wall_clock_minutes",
        "stale_after_seconds",
        "max_retries_per_task",
        "implementation_max_files_touched",
        "implementation_max_diff_lines",
        "experiment_max_wall_clock_minutes",
        "idle_sleep_seconds",
        "max_idle_sleep_seconds",
        "max_runner_session_minutes",
        "max_runner_session_rounds",
        "queue_planner_max_generated_tasks",
        "program_max_active_workflows",
        "program_max_failed_workflows_per_lane",
        "program_max_experiments_per_day",
        "program_gpu_budget_minutes_per_day",
    ):
        value = merged.get(field)
        if not isinstance(value, int) or value < 0:
            raise SchemaValidationError(f"`{field}` must be a non-negative integer.")
    allowed = merged.get("allowed_unattended_workflow_kinds")
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise SchemaValidationError("`allowed_unattended_workflow_kinds` must be a string list.")
    risk = merged.get("default_unattended_risk_level")
    if not isinstance(risk, str) or risk not in ALLOWED_RISK_LEVELS:
        raise SchemaValidationError(f"`default_unattended_risk_level` must be one of {ALLOWED_RISK_LEVELS}.")
    for field in (
        "implementation_allowed_command_prefixes",
        "implementation_forbidden_command_prefixes",
        "implementation_forbidden_command_substrings",
        "experiment_allowed_command_prefixes",
        "experiment_forbidden_command_prefixes",
        "experiment_forbidden_command_substrings",
        "experiment_required_artifacts",
        "queue_planner_allowed_templates",
    ):
        values = merged.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise SchemaValidationError(f"`{field}` must be a string list.")
    for field in ("queue_planner_max_budget_level", "queue_planner_active_lane"):
        if not isinstance(merged.get(field), str):
            raise SchemaValidationError(f"`{field}` must be a string.")
    for field in (
        "pause_on_review_revise",
        "night_mode_low_risk_only",
        "allow_unattended_implementation",
        "allow_unattended_experiment",
        "implementation_require_all_checks_pass",
        "implementation_pause_on_partial_write",
        "implementation_require_pwsh_for_checks",
        "experiment_require_summary_json",
        "experiment_require_metrics",
        "experiment_pause_on_missing_artifacts",
        "wake_on_stale_run",
        "wake_on_cooldown_expiry",
        "wake_on_task_registry_change",
        "enable_queue_planner",
        "queue_planner_require_closeout_pass",
        "queue_planner_allow_auxiliary_tasks",
        "enable_workflow_engine",
        "program_pause_on_budget_exhausted",
    ):
        if not isinstance(merged.get(field), bool):
            raise SchemaValidationError(f"`{field}` must be a boolean.")
    backoff = merged.get("backoff_multiplier")
    if not isinstance(backoff, (int, float)) or float(backoff) < 1.0:
        raise SchemaValidationError("`backoff_multiplier` must be a number >= 1.0.")
    return ValidationResult(data=merged)


def validate_role_workspace(data: dict[str, Any]) -> ValidationResult:
    _require_string(data, "run_id")
    role = _require_string(data, "role")
    if role not in ALLOWED_WORKSPACE_ROLES:
        raise SchemaValidationError(f"`role` must be one of {ALLOWED_WORKSPACE_ROLES}.")
    workspace_kind = _require_string(data, "workspace_kind")
    if workspace_kind not in ALLOWED_WORKSPACE_KINDS:
        raise SchemaValidationError(f"`workspace_kind` must be one of {ALLOWED_WORKSPACE_KINDS}.")
    _require_optional_string(data, "task_id")
    _require_optional_string(data, "linked_experiment_id")
    _require_string(data, "role_prompt_path")
    _require_string(data, "window_template_path")
    allowed_input_files = data.get("allowed_input_files")
    if not isinstance(allowed_input_files, list) or not all(isinstance(item, str) and item.strip() for item in allowed_input_files):
        raise SchemaValidationError("`allowed_input_files` must be a non-empty string list.")
    _require_string(data, "required_output_file")
    _require_string(data, "required_output_path")
    input_bundle = _require_mapping(data, "input_bundle")
    if not input_bundle:
        raise SchemaValidationError("`input_bundle` must not be empty.")
    write_constraints = data.get("write_constraints")
    if not isinstance(write_constraints, list) or not all(isinstance(item, str) and item.strip() for item in write_constraints):
        raise SchemaValidationError("`write_constraints` must be a non-empty string list.")
    _require_string(data, "next_step_instruction")

    if role == "executor":
        allowed_actions = data.get("allowed_actions")
        if not isinstance(allowed_actions, list) or not all(isinstance(item, str) and item.strip() for item in allowed_actions):
            raise SchemaValidationError("`allowed_actions` must be a non-empty string list for executor workspace.")
    if role == "reviewer":
        review_policy = data.get("review_policy")
        if not isinstance(review_policy, list) or not all(isinstance(item, str) and item.strip() for item in review_policy):
            raise SchemaValidationError("`review_policy` must be a non-empty string list for reviewer workspace.")
    return ValidationResult(data=data)


def validate_task_record(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(
        data,
        {
            "priority": 100,
            "retry_count": 0,
            "last_attempt_at": "",
            "cooldown_until": "",
            "autopilot_enabled": True,
            "required_checks": [],
            "skill_args": {},
            "experiment_command": "",
            "experiment_run_dir": "",
            "experiment_required_artifacts": [],
            "experiment_config_path": "",
            "blocked_reason_code": "",
            "blocked_reason_detail": "",
            "suggested_next_actions": [],
            "generated_by": "",
            "generation_reason": "",
            "source_evidence_ids": [],
            "template_name": "",
            "workflow_signal": {},
            "decision_payload": {},
        },
    )
    _require_string(merged, "task_id")
    _require_string(merged, "title")
    _require_string(merged, "task_doc_path")
    status = _require_string(merged, "status")
    if status not in ALLOWED_TASK_STATUSES:
        raise SchemaValidationError(f"`status` must be one of {ALLOWED_TASK_STATUSES}.")
    _require_string(merged, "objective")
    _require_string(merged, "workflow_kind")
    _require_string(merged, "risk_level")
    _require_string_list(merged, "success_criteria", allow_empty=True)
    _require_string_list(merged, "allowed_workflows", allow_empty=True)
    _require_string_list(merged, "allowed_write_paths", allow_empty=True)
    _require_string_list(merged, "required_checks", allow_empty=True)
    if not isinstance(merged.get("skill_args"), dict):
        raise SchemaValidationError("`skill_args` must be an object.")
    _require_optional_string(merged, "experiment_command")
    _require_optional_string(merged, "experiment_run_dir")
    _require_optional_string(merged, "experiment_config_path")
    _require_string_list(merged, "experiment_required_artifacts", allow_empty=True)
    _require_string_list(merged, "linked_experiments", allow_empty=True)
    _require_string_list(merged, "suggested_next_actions", allow_empty=True)
    _require_string_list(merged, "source_evidence_ids", allow_empty=True)
    for field in ("current_owner", "blocked_reason", "last_run_id", "created_at", "updated_at"):
        _require_optional_string(merged, field)
    for field in ("blocked_reason_code", "blocked_reason_detail", "generated_by", "generation_reason", "template_name"):
        _require_optional_string(merged, field)
    if not isinstance(merged.get("priority"), int):
        raise SchemaValidationError("`priority` must be an integer.")
    if not isinstance(merged.get("retry_count"), int) or merged["retry_count"] < 0:
        raise SchemaValidationError("`retry_count` must be a non-negative integer.")
    for field in ("last_attempt_at", "cooldown_until"):
        _require_optional_string(merged, field)
    if not isinstance(merged.get("autopilot_enabled"), bool):
        raise SchemaValidationError("`autopilot_enabled` must be a boolean.")
    workflow_signal = merged.get("workflow_signal", {})
    if not isinstance(workflow_signal, dict):
        raise SchemaValidationError("`workflow_signal` must be an object.")
    merged["decision_payload"] = _normalize_decision_payload(merged.get("decision_payload", {}))
    return ValidationResult(data=merged)


def validate_experiment_record(data: dict[str, Any]) -> ValidationResult:
    merged = {
        "workflow_signal": {},
        **data,
    }
    _require_string(merged, "experiment_id")
    _require_string(merged, "task_id")
    _require_string(merged, "run_dir")
    _require_string(merged, "summary_path")
    _require_optional_string(merged, "config_path")
    _require_string(merged, "variant")
    seed = merged.get("seed")
    if not isinstance(seed, (int, str)):
        raise SchemaValidationError("`seed` must be an integer or string.")
    status = _require_string(merged, "status")
    if status not in ALLOWED_EXPERIMENT_STATUSES:
        raise SchemaValidationError(f"`status` must be one of {ALLOWED_EXPERIMENT_STATUSES}.")
    closeout_status = _require_string(merged, "closeout_status")
    if closeout_status not in ALLOWED_CLOSEOUT_STATUSES:
        raise SchemaValidationError(f"`closeout_status` must be one of {ALLOWED_CLOSEOUT_STATUSES}.")
    _require_optional_string(merged, "review_verdict")
    _require_optional_string(merged, "metrics_val_path")
    _require_optional_string(merged, "metrics_test_path")
    _require_optional_string(merged, "last_verified_at")
    if not isinstance(merged.get("best_epoch"), (int, float, type(None))):
        raise SchemaValidationError("`best_epoch` must be numeric or null.")
    for field in ("best_val_l3_macro_f1", "best_val_multilabel_micro_f1"):
        if not isinstance(merged.get(field), (int, float, type(None))):
            raise SchemaValidationError(f"`{field}` must be numeric or null.")
    if not isinstance(merged.get("mean_gates"), dict):
        raise SchemaValidationError("`mean_gates` must be an object.")
    gate_health = merged.get("gate_health", {})
    if not isinstance(gate_health, dict):
        raise SchemaValidationError("`gate_health` must be an object.")
    workflow_signal = merged.get("workflow_signal", {})
    if not isinstance(workflow_signal, dict):
        raise SchemaValidationError("`workflow_signal` must be an object.")
    return ValidationResult(data=merged)


def validate_task_index(data: dict[str, Any]) -> ValidationResult:
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not all(isinstance(item, str) for item in tasks):
        raise SchemaValidationError("`tasks` must be a string list.")
    return ValidationResult(data=data)


def validate_experiment_index(data: dict[str, Any]) -> ValidationResult:
    experiments = data.get("experiments")
    if not isinstance(experiments, list) or not all(isinstance(item, str) for item in experiments):
        raise SchemaValidationError("`experiments` must be a string list.")
    return ValidationResult(data=data)


def validate_stage_checkpoint(data: dict[str, Any]) -> ValidationResult:
    merged = {
        "checkpoint_version": 1,
        "resume_hint": "",
        "artifacts_ready": {},
        **data,
    }
    for field in ("run_id", "task_id", "runner_id", "stage", "state_status", "updated_at", "resume_hint"):
        _require_string(merged, field, allow_empty=(field in ("task_id", "runner_id", "resume_hint")))
    if merged["stage"] not in ALLOWED_CHECKPOINT_STAGES:
        raise SchemaValidationError(f"`stage` must be one of {ALLOWED_CHECKPOINT_STAGES}.")
    if not isinstance(merged.get("checkpoint_version"), int) or int(merged["checkpoint_version"]) < 1:
        raise SchemaValidationError("`checkpoint_version` must be a positive integer.")
    artifacts_ready = merged.get("artifacts_ready")
    if not isinstance(artifacts_ready, dict) or not all(isinstance(key, str) and isinstance(value, bool) for key, value in artifacts_ready.items()):
        raise SchemaValidationError("`artifacts_ready` must be a string->bool object.")
    return ValidationResult(data=merged)


def validate_runtime_session(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_runtime_session())
    for field in ("runner_id", "started_at", "last_heartbeat_at", "last_wake_reason", "session_end_reason", "last_run_id", "last_task_id"):
        _require_optional_string(merged, field)
    for field in ("rounds_completed", "idle_cycles"):
        if not isinstance(merged.get(field), int) or int(merged[field]) < 0:
            raise SchemaValidationError(f"`{field}` must be a non-negative integer.")
    return ValidationResult(data=merged)


def validate_queue_planner_state(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_queue_planner_state())
    if not isinstance(merged.get("planner_version"), int) or int(merged["planner_version"]) < 1:
        raise SchemaValidationError("`planner_version` must be a positive integer.")
    for field in ("active_lane", "last_planner_run_at"):
        _require_optional_string(merged, field)
    for field in ("last_generated_task_ids", "suppressed_candidates"):
        values = merged.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise SchemaValidationError(f"`{field}` must be a string list.")
    history = merged.get("generation_history")
    if not isinstance(history, list):
        raise SchemaValidationError("`generation_history` must be a list.")
    normalized_history: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            raise SchemaValidationError("`generation_history` items must be objects.")
        timestamp = item.get("timestamp", "")
        generated_task_ids = item.get("generated_task_ids", [])
        if not isinstance(timestamp, str):
            raise SchemaValidationError("`generation_history.timestamp` must be a string.")
        if not isinstance(generated_task_ids, list) or not all(isinstance(entry, str) for entry in generated_task_ids):
            raise SchemaValidationError("`generation_history.generated_task_ids` must be a string list.")
        normalized_history.append(
            {
                "timestamp": timestamp,
                "generated_task_ids": generated_task_ids,
                "reason": str(item.get("reason", "")),
            }
        )
    merged["generation_history"] = normalized_history
    return ValidationResult(data=merged)


def validate_program_state(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_program_state())
    for field in (
        "program_id",
        "primary_goal",
        "active_lane",
        "active_workflow_id",
        "status",
        "current_milestone",
        "active_milestone",
        "last_program_summary",
        "next_workflow_template",
        "next_recommended_workflow",
        "program_block_reason",
    ):
        _require_optional_string(merged, field)
    for field in ("completed_milestones", "blocked_milestones", "next_candidate_workflows", "decision_memory_summary"):
        values = merged.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise SchemaValidationError(f"`{field}` must be a string list.")
    if not isinstance(merged.get("resume_after_budget_reset"), bool):
        raise SchemaValidationError("`resume_after_budget_reset` must be a boolean.")
    return ValidationResult(data=merged)


def validate_milestones_state(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_milestones_state())
    _require_optional_string(merged, "program_id")
    milestones = merged.get("milestones")
    if not isinstance(milestones, list):
        raise SchemaValidationError("`milestones` must be a list.")
    normalized: list[dict[str, Any]] = []
    for item in milestones:
        if not isinstance(item, dict):
            raise SchemaValidationError("`milestones` items must be objects.")
        milestone = {
            "milestone_id": str(item.get("milestone_id", "")),
            "title": str(item.get("title", "")),
            "status": str(item.get("status", "pending")),
            "entry_conditions": list(item.get("entry_conditions", [])),
            "success_conditions": list(item.get("success_conditions", [])),
            "linked_workflow_template": str(item.get("linked_workflow_template", "")),
            "linked_topic": str(item.get("linked_topic", "")),
            "source_evidence_ids": list(item.get("source_evidence_ids", [])),
            "last_evaluated_at": str(item.get("last_evaluated_at", "")),
            "block_reason": str(item.get("block_reason", "")),
            "auto_resume_allowed": bool(item.get("auto_resume_allowed", False)),
        }
        if milestone["status"] not in ("pending", "active", "completed", "blocked", "paused_for_human"):
            raise SchemaValidationError("`milestones.status` contains an unsupported value.")
        for field in ("entry_conditions", "success_conditions", "source_evidence_ids"):
            values = milestone[field]
            if not isinstance(values, list) or not all(isinstance(entry, str) for entry in values):
                raise SchemaValidationError(f"`milestones.{field}` must be a string list.")
        normalized.append(milestone)
    merged["milestones"] = normalized
    return ValidationResult(data=merged)


def validate_workflow_state(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_workflow_state())
    for field in ("workflow_id", "template_name", "lane", "status", "current_stage", "blocked_stage", "block_reason", "last_transition_at"):
        _require_optional_string(merged, field)
    if merged["template_name"] and merged["template_name"] not in ALLOWED_WORKFLOW_TEMPLATES:
        raise SchemaValidationError(f"`template_name` must be one of {ALLOWED_WORKFLOW_TEMPLATES}.")
    if merged["status"] not in ALLOWED_WORKFLOW_STATUSES:
        raise SchemaValidationError(f"`status` must be one of {ALLOWED_WORKFLOW_STATUSES}.")
    for field in ("completed_stages", "generated_task_ids", "source_evidence_ids"):
        values = merged.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise SchemaValidationError(f"`{field}` must be a string list.")
    workflow_signal = merged.get("workflow_signal", {})
    if not isinstance(workflow_signal, dict):
        raise SchemaValidationError("`workflow_signal` must be an object.")
    return ValidationResult(data=merged)


def validate_program_budget_state(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_program_budget_state())
    for field in ("date", "last_reset_at", "budget_window_status"):
        _require_optional_string(merged, field)
    for field in ("experiments_run_today", "gpu_budget_minutes_used"):
        if not isinstance(merged.get(field), int) or int(merged[field]) < 0:
            raise SchemaValidationError(f"`{field}` must be a non-negative integer.")
    return ValidationResult(data=merged)


def validate_best_known_metrics(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_best_known_metrics())
    for field in ("lane", "best_gate_health_status", "source_experiment_id", "last_updated_at"):
        _require_optional_string(merged, field)
    for field in ("best_val_l3_macro_f1", "best_val_multilabel_micro_f1", "best_test_multilabel_micro_f1"):
        if not isinstance(merged.get(field), (int, float, type(None))):
            raise SchemaValidationError(f"`{field}` must be numeric or null.")
    mean_gates = merged.get("best_mean_gates")
    if not isinstance(mean_gates, dict):
        raise SchemaValidationError("`best_mean_gates` must be an object.")
    return ValidationResult(data=merged)


def validate_program_handoff(data: dict[str, Any]) -> ValidationResult:
    merged = _merged(data, default_program_handoff())
    for field in (
        "program_id",
        "primary_goal",
        "active_lane",
        "active_milestone",
        "block_reason",
        "next_recommended_workflow",
        "next_ready_task_id",
        "next_ready_task_template",
        "program_stop_reason",
        "updated_at",
    ):
        _require_optional_string(merged, field)
    for field in ("completed_milestones", "top_decisions"):
        values = merged.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise SchemaValidationError(f"`{field}` must be a string list.")
    if not isinstance(merged.get("best_known_metrics_snapshot"), dict):
        raise SchemaValidationError("`best_known_metrics_snapshot` must be an object.")
    return ValidationResult(data=merged)


def ensure_runtime_state_files(default_intervention_policy: dict[str, Any]) -> None:
    LOOP_STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOOP_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    TASK_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENT_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    WORKFLOW_STATE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_parent(EVENTS_PATH)

    if not CURRENT_STATE_PATH.exists():
        write_json(CURRENT_STATE_PATH, default_current_state())
    else:
        write_json(CURRENT_STATE_PATH, validate_current_state(load_json(CURRENT_STATE_PATH)).data)

    if not ACTIVE_OBJECTIVE_PATH.exists():
        write_json(ACTIVE_OBJECTIVE_PATH, default_active_objective())
    else:
        write_json(ACTIVE_OBJECTIVE_PATH, validate_active_objective(load_json(ACTIVE_OBJECTIVE_PATH)).data)

    if not INTERVENTION_POLICY_PATH.exists():
        write_json(INTERVENTION_POLICY_PATH, default_intervention_policy)
    else:
        merged_policy = dict(default_intervention_policy)
        merged_policy.update(load_json(INTERVENTION_POLICY_PATH))
        write_json(INTERVENTION_POLICY_PATH, validate_intervention_policy(merged_policy).data)

    if not TASK_INDEX_PATH.exists():
        write_json(TASK_INDEX_PATH, default_task_index())
    else:
        write_json(TASK_INDEX_PATH, validate_task_index(load_json(TASK_INDEX_PATH)).data)

    if not EXPERIMENT_INDEX_PATH.exists():
        write_json(EXPERIMENT_INDEX_PATH, default_experiment_index())
    else:
        write_json(EXPERIMENT_INDEX_PATH, validate_experiment_index(load_json(EXPERIMENT_INDEX_PATH)).data)

    if not EVENTS_PATH.exists():
        EVENTS_PATH.write_text("", encoding="utf-8")
    if not RUNTIME_SESSION_PATH.exists():
        write_json(RUNTIME_SESSION_PATH, default_runtime_session())
    else:
        write_json(RUNTIME_SESSION_PATH, validate_runtime_session(load_json(RUNTIME_SESSION_PATH)).data)
    if not RUNTIME_SESSION_HISTORY_PATH.exists():
        RUNTIME_SESSION_HISTORY_PATH.write_text("", encoding="utf-8")
    if not QUEUE_PLANNER_STATE_PATH.exists():
        write_json(QUEUE_PLANNER_STATE_PATH, default_queue_planner_state())
    else:
        try:
            write_json(QUEUE_PLANNER_STATE_PATH, validate_queue_planner_state(load_json(QUEUE_PLANNER_STATE_PATH)).data)
        except (json.JSONDecodeError, OSError, SchemaValidationError, ValueError):
            write_json(QUEUE_PLANNER_STATE_PATH, default_queue_planner_state())
    if not PROGRAM_STATE_PATH.exists():
        write_json(PROGRAM_STATE_PATH, default_program_state())
    else:
        write_json(PROGRAM_STATE_PATH, validate_program_state(load_json(PROGRAM_STATE_PATH)).data)
    if not MILESTONES_PATH.exists():
        write_json(MILESTONES_PATH, default_milestones_state())
    else:
        write_json(MILESTONES_PATH, validate_milestones_state(load_json(MILESTONES_PATH)).data)
    if not DECISION_MEMORY_PATH.exists():
        DECISION_MEMORY_PATH.write_text("", encoding="utf-8")
    if not PROGRAM_BUDGET_STATE_PATH.exists():
        write_json(PROGRAM_BUDGET_STATE_PATH, default_program_budget_state())
    else:
        write_json(PROGRAM_BUDGET_STATE_PATH, validate_program_budget_state(load_json(PROGRAM_BUDGET_STATE_PATH)).data)
    if not BEST_KNOWN_METRICS_PATH.exists():
        write_json(BEST_KNOWN_METRICS_PATH, default_best_known_metrics())
    else:
        write_json(BEST_KNOWN_METRICS_PATH, validate_best_known_metrics(load_json(BEST_KNOWN_METRICS_PATH)).data)
    if not PROGRAM_HANDOFF_PATH.exists():
        write_json(PROGRAM_HANDOFF_PATH, default_program_handoff())
    else:
        try:
            write_json(PROGRAM_HANDOFF_PATH, validate_program_handoff(load_json(PROGRAM_HANDOFF_PATH)).data)
        except (json.JSONDecodeError, OSError, SchemaValidationError, ValueError):
            write_json(PROGRAM_HANDOFF_PATH, default_program_handoff())
