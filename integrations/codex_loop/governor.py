from __future__ import annotations

from datetime import datetime
from time import perf_counter
from pathlib import Path
from typing import Any

from integrations.codex_loop.artifacts import (
    build_experiment_registry_draft,
    collect_task_artifacts,
    parse_json_output,
    text_excerpt,
)
from integrations.codex_loop.checkpoint import load_stage_checkpoint, write_stage_checkpoint
from integrations.codex_loop.constants import (
    ACTIVE_OBJECTIVE_PATH,
    ALLOWED_EXPERIMENT_STATUSES,
    AUTOCONTINUE_WORKFLOW_KINDS,
    CURRENT_STATE_PATH,
    DEFAULT_INTERVENTION_POLICY,
    EXECUTION_RESULT_NAME,
    EXECUTION_RESULT_TEMPLATE_NAME,
    EXECUTOR_PROMPT_PATH,
    EXECUTOR_WINDOW_TEMPLATE_PATH,
    EXPERIMENT_INDEX_PATH,
    EXPERIMENT_PROMPT_PATH,
    EXPERIMENT_REGISTRY_DIR,
    EXPERIMENT_WINDOW_TEMPLATE_PATH,
    FORBIDDEN_ARG_TOKENS,
    FORBIDDEN_WRITE_TOKENS,
    HANDOFF_DIR,
    HANDOFF_TEMPLATE_NAME,
    IMPLEMENTATION_PROMPT_PATH,
    IMPLEMENTATION_WINDOW_TEMPLATE_PATH,
    LOOP_RUNS_DIR,
    LOOP_STATE_DIR,
    PLANNER_DECISION_NAME,
    PLANNER_DECISION_TEMPLATE_NAME,
    PLANNER_PACKET_NAME,
    PLANNER_PROMPT_PATH,
    PLANNER_WINDOW_TEMPLATE_PATH,
    REPORTS_DIR,
    REPORT_TEMPLATE_NAME,
    REPO_ROOT,
    REVIEWER_PROMPT_PATH,
    REVIEWER_WINDOW_TEMPLATE_PATH,
    REVIEW_VERDICT_NAME,
    REVIEW_VERDICT_TEMPLATE_NAME,
    ROUND_SUMMARY_NAME,
    SCHEMA_VERSION,
    STAGE_CHECKPOINT_NAME,
    TASK_INDEX_PATH,
    TASK_REGISTRY_DIR,
    TASK_TYPE_TO_SKILL,
)
from integrations.codex_loop.context_builder import build_context_packet
from integrations.codex_loop.executor_runner import CommandResult, run_skill
from integrations.codex_loop.implementation_runner import execute_implementation
from integrations.codex_loop.experiment_runner import execute_experiment
from integrations.codex_loop.policy import load_policy
from integrations.codex_loop.schemas import (
    SchemaValidationError,
    ensure_runtime_state_files,
    load_json,
    validate_current_state,
    validate_execution_result,
    validate_experiment_index,
    validate_experiment_record,
    validate_planner_decision,
    validate_review_verdict,
    validate_role_workspace,
    validate_task_index,
    validate_task_record,
    write_json,
)


class GovernorError(RuntimeError):
    """Raised when the governor must stop the current loop step."""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_run_id() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S")


def _load_state() -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    return validate_current_state(load_json(CURRENT_STATE_PATH)).data


def _write_state(state: dict[str, Any]) -> None:
    validate_current_state(state)
    write_json(CURRENT_STATE_PATH, state)


def _write_active_objective(objective: str, task_type: str, success_definition: list[str]) -> None:
    write_json(
        ACTIVE_OBJECTIVE_PATH,
        {
            "objective": objective,
            "task_type": task_type,
            "owner": "planner",
            "success_definition": success_definition,
        },
    )


def _run_dir(run_id: str) -> Path:
    return LOOP_RUNS_DIR / run_id


def _pause_actions(reason_code: str, detail: str = "", evidence: dict[str, Any] | None = None) -> list[str]:
    evidence = evidence or {}
    write_set = [str(item) for item in evidence.get("write_set", []) if str(item).strip()]
    checks_run = [str(item) for item in evidence.get("checks_run", []) if str(item).strip()]
    checks_passed = {str(item) for item in evidence.get("checks_passed", []) if str(item).strip()}
    detected_conditions = [str(item) for item in evidence.get("detected_conditions", []) if str(item).strip()]
    failed_checks = [item for item in checks_run if item not in checks_passed]
    mapping = {
        "implementation_required_checks_failed": [
            f"查看失败 check 输出：`{failed_checks[0]}`。" if failed_checks else "查看失败 check 输出。",
            "缩小 write set 或 objective。",
            "必要时改回手动三窗口模式。",
        ],
        "implementation_write_scope_violation": [
            f"检查越界写入是否来自：`{write_set[0]}`。" if write_set else "检查 allowed_write_paths 是否过宽或过窄。",
            "确认是否需要更细的 implementation trial task。",
            "必要时人工接管并手动 review。",
        ],
        "planner_gate": [
            f"优先检查 planner gate 细节：{detail}" if detail else "修正 planner decision。",
            "补齐 required checks 或 write scope。",
            "从 planner 阶段恢复并重试。",
        ],
        "two_rounds_no_progress": [
            "检查 progress fingerprint 是否没有变化。",
            "缩小 objective 或切换为人工推进。",
            "必要时暂停当前 task 并重排优先级。",
        ],
    }
    return mapping.get(
        reason_code,
        [
            f"先看 detected_conditions：`{detected_conditions[0]}`。" if detected_conditions else "查看对应 run 的 round_summary 与 execution/review 产物。",
            "确认是否需要人工接管当前 task。",
        ],
    )


def _structured_block(reason_code: str, detail: str = "", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "blocked_reason": detail or reason_code,
        "blocked_reason_code": reason_code,
        "blocked_reason_detail": detail or reason_code,
        "suggested_next_actions": _pause_actions(reason_code, detail=detail, evidence=evidence),
    }


def _review_evidence(execution: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    verdict_evidence = verdict.get("evidence", {})
    machine = execution.get("machine_assessment", {})
    return {
        "write_set": list(verdict_evidence.get("write_set", execution.get("write_set", []))),
        "checks_run": list(verdict_evidence.get("checks_run", execution.get("checks_run", []))),
        "checks_passed": list(verdict_evidence.get("checks_passed", execution.get("checks_passed", []))),
        "detected_conditions": list(
            verdict_evidence.get("detected_conditions", machine.get("detected_conditions", []))
        ),
    }


def _bounded_decision_payload(topic: str, stdout_json: dict[str, Any] | None = None) -> dict[str, Any]:
    stdout_json = stdout_json if isinstance(stdout_json, dict) else {}
    if topic == "multilabel_inference_protocol":
        return {
            "topic": "multilabel_inference_selector",
            "chosen_protocol": str(stdout_json.get("chosen_protocol", "")).strip() or "dual_output_without_selector",
            "rejected_protocols": list(stdout_json.get("rejected_protocols", ["selector_first", "rule_based_activation_only"])),
            "requires_selector_experiment": bool(stdout_json.get("requires_selector_experiment", False)),
            "ready_for_implementation": bool(stdout_json.get("ready_for_implementation", True)),
            "next_action_hint": str(stdout_json.get("next_action_hint", "")).strip() or "promotion_candidate_followup",
        }
    if topic == "promotion_candidate_followup":
        return {
            "topic": "promotion_candidate_followup",
            "chosen_protocol": str(stdout_json.get("chosen_protocol", "")).strip() or "dual_output_without_selector",
            "rejected_protocols": list(stdout_json.get("rejected_protocols", ["selector_feasibility_smoke", "hold_no_experiment"])),
            "requires_selector_experiment": bool(stdout_json.get("requires_selector_experiment", False)),
            "ready_for_implementation": bool(stdout_json.get("ready_for_implementation", True)),
            "next_action_hint": str(stdout_json.get("next_action_hint", "")).strip() or "dual_output_implementation_plan",
        }
    if topic == "dual_output_implementation_plan":
        requires_runtime_api_change = bool(stdout_json.get("requires_runtime_api_change", True))
        requires_model_output_change = bool(stdout_json.get("requires_model_output_change", True))
        next_action_hint = str(stdout_json.get("next_action_hint", "")).strip()
        if not next_action_hint:
            if requires_runtime_api_change or requires_model_output_change:
                next_action_hint = "dual_output_runtime_patch"
            else:
                next_action_hint = "dual_output_report_closeout"
        return {
            "topic": "dual_output_implementation_plan",
            "chosen_protocol": str(stdout_json.get("chosen_protocol", "")).strip() or "dual_output_without_selector",
            "rejected_protocols": list(stdout_json.get("rejected_protocols", ["selector_first", "hold_no_implementation"])),
            "ready_for_implementation": bool(stdout_json.get("ready_for_implementation", True)),
            "implementation_scope": str(stdout_json.get("implementation_scope", "")).strip() or "dual_output_runtime_and_model_outputs",
            "requires_runtime_api_change": requires_runtime_api_change,
            "requires_model_output_change": requires_model_output_change,
            "next_action_hint": next_action_hint,
        }
    return {}


def _decision_payload_for_truth_calibration(decision: dict[str, Any], stdout_json: dict[str, Any] | None = None) -> dict[str, Any]:
    task_record_path = _task_record_path(decision["task_id"])
    if not task_record_path.exists():
        return {}
    task_record = _load_task_record(decision["task_id"])
    skill_args = dict(task_record.get("skill_args", {}))
    topic = str(skill_args.get("topic", "")).strip()
    if not topic:
        return {}
    payload = _bounded_decision_payload(topic, stdout_json=stdout_json)
    return payload if any(str(value).strip() for value in payload.values() if not isinstance(value, list)) or payload.get("rejected_protocols") else {}


def _canonical_reason_code(issue_text: str) -> str:
    text = str(issue_text or "").strip()
    if not text:
        return "paused_for_human"
    if text.startswith("failed_required_check:") or text.startswith("missing_required_check:"):
        return "implementation_required_checks_failed"
    if text.startswith("implementation_forbidden_check_prefix"):
        return "implementation_forbidden_check_prefix"
    if text.startswith("implementation_forbidden_command_prefix"):
        return "implementation_forbidden_command_prefix"
    if text.startswith("implementation_forbidden_command_substring"):
        return "implementation_forbidden_command_substring"
    return text


def _apply_block_to_task(record: dict[str, Any], reason_code: str, detail: str = "", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    record.update(_structured_block(reason_code, detail, evidence=evidence))
    return record


def _apply_block_to_state(state: dict[str, Any], reason_code: str, detail: str = "", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    state["last_blocker_code"] = reason_code
    state["blocked_reason_code"] = reason_code
    state["blocked_reason_detail"] = detail or reason_code
    state["suggested_next_actions"] = _pause_actions(reason_code, detail=detail, evidence=evidence)
    return state


def _workspace_path(run_id: str, workspace_kind: str) -> Path:
    run_dir = _run_dir(run_id)
    return run_dir / f"{workspace_kind}_workspace.json"


def _resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def _relative_or_absolute(path: Path) -> str:
    return str(path.resolve())


def _load_task_index() -> dict[str, Any]:
    return validate_task_index(load_json(TASK_INDEX_PATH)).data


def _save_task_index(index: dict[str, Any]) -> None:
    validate_task_index(index)
    write_json(TASK_INDEX_PATH, index)


def _task_record_path(task_id: str) -> Path:
    return TASK_REGISTRY_DIR / f"{task_id}.json"


def _load_task_record(task_id: str) -> dict[str, Any]:
    return validate_task_record(load_json(_task_record_path(task_id))).data


def _save_task_record(record: dict[str, Any]) -> None:
    validated = validate_task_record(record).data
    write_json(_task_record_path(validated["task_id"]), validated)
    index = _load_task_index()
    tasks = list(index.get("tasks", []))
    if validated["task_id"] not in tasks:
        tasks.append(validated["task_id"])
        tasks.sort()
        _save_task_index({"tasks": tasks})


def _load_experiment_index() -> dict[str, Any]:
    return validate_experiment_index(load_json(EXPERIMENT_INDEX_PATH)).data


def _save_experiment_index(index: dict[str, Any]) -> None:
    validate_experiment_index(index)
    write_json(EXPERIMENT_INDEX_PATH, index)


def _experiment_record_path(experiment_id: str) -> Path:
    return EXPERIMENT_REGISTRY_DIR / f"{experiment_id}.json"


def _load_experiment_record(experiment_id: str) -> dict[str, Any]:
    return validate_experiment_record(load_json(_experiment_record_path(experiment_id))).data


def _save_experiment_record(record: dict[str, Any]) -> None:
    validated = validate_experiment_record(record).data
    write_json(_experiment_record_path(validated["experiment_id"]), validated)
    index = _load_experiment_index()
    experiments = list(index.get("experiments", []))
    if validated["experiment_id"] not in experiments:
        experiments.append(validated["experiment_id"])
        experiments.sort()
        _save_experiment_index({"experiments": experiments})


def _slug_from_task_file(task_file: Path) -> str:
    return task_file.stem


def _title_from_task_file(task_file: Path) -> str:
    for line in task_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return task_file.stem


def _base_write_constraints(required_output_name: str, required_output_path: Path) -> list[str]:
    return [
        f"Only write `{required_output_name}` for this role.",
        f"Do not edit files outside `{required_output_path}`.",
        "Do not modify loop_state files directly.",
        "Do not overwrite another role's output file.",
    ]


def _write_workspace(role: str, payload: dict[str, Any]) -> Path:
    validate_role_workspace(payload)
    output_path = _workspace_path(payload["run_id"], payload["workspace_kind"])
    write_json(output_path, payload)
    return output_path


def _record_command(kind: str, result: CommandResult, stdout_json: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "kind": kind,
        "name": result.skill,
        "command": result.command,
        "args": result.args,
        "exit_code": result.exit_code,
        "stdout_excerpt": text_excerpt(result.stdout),
        "stderr_excerpt": text_excerpt(result.stderr),
        "stdout_json": stdout_json,
    }


def _merge_action_args(workflow_kind: str, action_kind: str, action_name: str, action_args: dict[str, Any]) -> dict[str, Any]:
    if action_kind in ("skill", "artifact_repair") and action_name in TASK_TYPE_TO_SKILL:
        merged = dict(TASK_TYPE_TO_SKILL[action_name]["default_args"])
        merged.update(action_args)
        return merged
    if workflow_kind in TASK_TYPE_TO_SKILL:
        merged = dict(TASK_TYPE_TO_SKILL[workflow_kind]["default_args"])
        merged.update(action_args)
        return merged
    return dict(action_args)


def _gate_planner_decision(decision: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    workflow_kind = decision["workflow_kind"]
    action = decision["action"]
    action_kind = action["kind"]

    if decision["needs_human_before_execute"]:
        reasons.append("planner requested human confirmation before execution.")

    for key, value in action["args"].items():
        key_text = str(key).lower()
        if any(token in key_text for token in FORBIDDEN_ARG_TOKENS):
            reasons.append(f"forbidden action arg key detected: {key}")
        if isinstance(value, str):
            lower_value = value.lower()
            if any(token in lower_value for token in FORBIDDEN_ARG_TOKENS):
                reasons.append(f"forbidden action arg value detected for `{key}`.")

    if workflow_kind in ("truth_calibration", "governance_refresh", "results_closeout", "multilabel_readiness_audit"):
        allowed = TASK_TYPE_TO_SKILL[workflow_kind]
        if action_kind != "skill":
            reasons.append(f"`{workflow_kind}` must use action.kind `skill`.")
        if action["name"] != allowed["skill"]:
            reasons.append(f"workflow `{workflow_kind}` must map to skill `{allowed['skill']}`, got `{action['name']}`.")
    elif workflow_kind == "artifact_repair":
        allowed = TASK_TYPE_TO_SKILL["artifact_repair"]
        if action_kind not in ("artifact_repair", "skill"):
            reasons.append("artifact_repair must use action.kind `artifact_repair` or `skill`.")
        if action["name"] != allowed["skill"]:
            reasons.append(f"artifact_repair must map to `{allowed['skill']}`, got `{action['name']}`.")
    elif workflow_kind == "implementation_task":
        if action_kind != "implementation":
            reasons.append("implementation_task must use action.kind `implementation`.")
        if not decision["allowed_write_paths"]:
            reasons.append("implementation_task requires non-empty `allowed_write_paths`.")
        if not decision["required_checks"]:
            reasons.append("implementation_task requires non-empty `required_checks`.")
    elif workflow_kind == "experiment_run":
        if action_kind != "experiment":
            reasons.append("experiment_run must use action.kind `experiment`.")
        if not decision["required_checks"]:
            reasons.append("experiment_run requires non-empty `required_checks`.")
        action_args = dict(action.get("args", {}))
        if not str(action_args.get("command", "")).strip():
            reasons.append("experiment_run requires non-empty `action.args.command`.")
        if not str(action_args.get("run_dir", "")).strip():
            reasons.append("experiment_run requires non-empty `action.args.run_dir`.")

    return reasons


def _gate_action_assets(decision: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    action = decision["action"]
    merged_args = _merge_action_args(decision["workflow_kind"], action["kind"], action["name"], action["args"])

    for key in ("run_dir", "config", "config_path", "report_path", "governance_dir", "vocab_path"):
        value = merged_args.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        path = _resolve_repo_path(value)
        if decision["workflow_kind"] == "experiment_run" and key == "run_dir":
            continue
        if not path.exists():
            reasons.append(f"required path for `{key}` does not exist: {path}")

    if decision["workflow_kind"] == "results_closeout":
        run_dir_value = merged_args.get("run_dir")
        runs_root_value = merged_args.get("runs_root")
        glob_value = merged_args.get("glob")
        strict_mode = bool(merged_args.get("strict_required_artifacts", False)) or str(merged_args.get("mode", "")).strip() == "strict_closeout"

        resolved_run_dirs: list[Path] = []
        if isinstance(run_dir_value, str) and run_dir_value.strip():
            resolved_run_dirs.append(_resolve_repo_path(run_dir_value))
        elif isinstance(run_dir_value, list):
            for item in run_dir_value:
                if isinstance(item, str) and item.strip():
                    resolved_run_dirs.append(_resolve_repo_path(item))
        elif isinstance(runs_root_value, str) and runs_root_value.strip() and isinstance(glob_value, str) and glob_value.strip():
            runs_root = _resolve_repo_path(runs_root_value)
            resolved_run_dirs.extend(sorted(path for path in runs_root.glob(glob_value) if path.is_dir()))

        if not resolved_run_dirs:
            reasons.append("results_closeout requires a non-empty `run_dir`, `run_dir[]`, or `runs_root + glob`.")
            return reasons

        for run_dir in resolved_run_dirs:
            for rel in ("summary.json", "logs/history.json"):
                if not (run_dir / rel).exists():
                    reasons.append(f"results_closeout base artifact missing before execution: {run_dir / rel}")
            if strict_mode:
                for rel in ("evaluation/metrics_val.json", "evaluation/metrics_test.json"):
                    if not (run_dir / rel).exists():
                        reasons.append(f"results_closeout strict artifact missing before execution: {run_dir / rel}")

    if decision["workflow_kind"] == "implementation_task":
        for item in decision["allowed_write_paths"]:
            normalized = item.replace("\\", "/").lower()
            if any(token in normalized for token in FORBIDDEN_WRITE_TOKENS):
                reasons.append(f"forbidden implementation write path detected: {item}")

    return reasons


def _fingerprint_from_payload(execution_payload: dict[str, Any]) -> str:
    progress_delta = execution_payload.get("progress_delta", {})
    fingerprint = progress_delta.get("fingerprint", "")
    if isinstance(fingerprint, str) and fingerprint.strip():
        return fingerprint
    action = execution_payload.get("action", {})
    write_set = execution_payload.get("write_set", [])
    checks_passed = execution_payload.get("checks_passed", [])
    return "|".join(
        [
            str(action.get("name", "")),
            ",".join(sorted(str(item) for item in write_set)),
            ",".join(sorted(str(item) for item in checks_passed)),
        ]
    )


def _build_machine_assessment(
    workflow_kind: str,
    preflight_result: CommandResult,
    action_result: CommandResult,
    action_stdout_json: dict[str, Any] | None,
    task_artifacts: dict[str, Any],
) -> dict[str, Any]:
    detected_conditions: list[str] = []
    fail_fast = False

    if preflight_result.exit_code != 0:
        fail_fast = True
        detected_conditions.append("active_truth_conflict")
    if action_result.exit_code != 0:
        fail_fast = True
        if workflow_kind == "governance_refresh":
            detected_conditions.append("governance_validation_failed")
        elif workflow_kind == "results_closeout":
            detected_conditions.append("results_closeout_strict_artifacts_missing")
        elif workflow_kind == "multilabel_readiness_audit":
            detected_conditions.append("audit_fail_item_detected")
        elif workflow_kind == "artifact_repair":
            detected_conditions.append("artifact_repair_failed")
    if workflow_kind == "governance_refresh" and not task_artifacts.get("summary_exists"):
        fail_fast = True
        detected_conditions.append("governance_summary_missing")
    if workflow_kind == "multilabel_readiness_audit" and task_artifacts.get("audit_fail_count", 0) > 0:
        fail_fast = True
        detected_conditions.append("audit_fail_item_detected")
    if workflow_kind == "results_closeout" and isinstance(action_stdout_json, dict) and action_stdout_json.get("status") == "strict_fail":
        fail_fast = True
        detected_conditions.append("results_closeout_strict_artifacts_missing")

    return {
        "fail_fast": fail_fast,
        "completed_execution": preflight_result.exit_code == 0 and action_result.exit_code == 0,
        "detected_conditions": detected_conditions,
    }


def _render_round_summary(decision: dict[str, Any], execution: dict[str, Any], verdict: dict[str, Any]) -> str:
    lines = [
        f"# Codex Loop Round Summary: {decision['run_id']}",
        "",
        "## Objective",
        f"- task_id: `{decision['task_id']}`",
        f"- phase: `{decision['phase']}`",
        f"- workflow_kind: `{decision['workflow_kind']}`",
        f"- objective: {decision['objective']}",
        "",
        "## Execution",
        f"- preflight: `{execution['preflight']['status']}` ({execution['preflight']['exit_code']})",
        f"- action kind: `{execution['action']['kind']}`",
        f"- action name: `{execution['action']['name']}`",
        f"- action exit_code: `{execution['action']['exit_code']}`",
        f"- fail_fast: `{execution['machine_assessment']['fail_fast']}`",
        "",
        "## Review",
        f"- verdict: `{verdict['verdict']}`",
        f"- objective_met: `{verdict['objective_met']}`",
        f"- drift_detected: `{verdict['drift_detected']}`",
        f"- needs_human: `{verdict['needs_human']}`",
        f"- next_mode: `{verdict['recommended_next_mode']}`",
        f"- next_objective: {verdict['next_objective']}",
        "",
    ]
    issues = verdict.get("issues", [])
    if issues:
        lines.extend(["## Issues"] + [f"- {item}" for item in issues] + [""])
    return "\n".join(lines).rstrip() + "\n"


def _default_task_record(
    task_file: Path,
    workflow_kind: str,
    objective: str,
    risk_level: str,
    allowed_write_paths: list[str],
    required_checks: list[str],
    skill_args: dict[str, Any] | None = None,
    experiment_command: str = "",
    experiment_run_dir: str = "",
    experiment_required_artifacts: list[str] | None = None,
    experiment_config_path: str = "",
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "task_id": _slug_from_task_file(task_file),
        "title": _title_from_task_file(task_file),
        "task_doc_path": str(task_file.resolve()),
        "status": "proposed",
        "objective": objective,
        "workflow_kind": workflow_kind,
        "risk_level": risk_level,
        "success_criteria": [],
        "allowed_workflows": [workflow_kind],
        "allowed_write_paths": allowed_write_paths,
        "required_checks": required_checks,
        "skill_args": dict(skill_args or {}),
        "experiment_command": experiment_command,
        "experiment_run_dir": experiment_run_dir,
        "experiment_required_artifacts": list(experiment_required_artifacts or []),
        "experiment_config_path": experiment_config_path,
        "linked_experiments": [],
        "current_owner": "planner",
        "blocked_reason": "",
        "blocked_reason_code": "",
        "blocked_reason_detail": "",
        "suggested_next_actions": [],
        "workflow_signal": {},
        "decision_payload": {},
        "last_run_id": "",
        "priority": 100,
        "retry_count": 0,
        "last_attempt_at": "",
        "cooldown_until": "",
        "autopilot_enabled": True,
        "created_at": now,
        "updated_at": now,
    }


def get_current_state() -> dict[str, Any]:
    return _load_state()


def get_task_record(task_id: str) -> dict[str, Any]:
    return _load_task_record(task_id)


def list_task_records() -> list[dict[str, Any]]:
    index = _load_task_index()
    return [_load_task_record(task_id) for task_id in index.get("tasks", [])]


def save_task_record(record: dict[str, Any]) -> Path:
    _save_task_record(record)
    return _task_record_path(record["task_id"])


def get_runtime_policy() -> dict[str, Any]:
    return load_policy()


def create_task(
    task_file: str,
    workflow_kind: str = "implementation_task",
    objective: str = "",
    risk_level: str = "medium",
    allowed_write_paths: list[str] | None = None,
    required_checks: list[str] | None = None,
    skill_args: dict[str, Any] | None = None,
    experiment_command: str = "",
    experiment_run_dir: str = "",
    experiment_required_artifacts: list[str] | None = None,
    experiment_config_path: str = "",
) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    task_path = _resolve_repo_path(task_file)
    if not task_path.exists():
        raise GovernorError(f"task file not found: {task_path}")
    record = _default_task_record(
        task_file=task_path,
        workflow_kind=workflow_kind,
        objective=objective or _title_from_task_file(task_path),
        risk_level=risk_level,
        allowed_write_paths=allowed_write_paths or [],
        required_checks=required_checks or [],
        skill_args=skill_args or {},
        experiment_command=experiment_command,
        experiment_run_dir=experiment_run_dir,
        experiment_required_artifacts=experiment_required_artifacts or [],
        experiment_config_path=experiment_config_path,
    )
    _save_task_record(record)
    state = _load_state()
    if not state.get("active_task_id"):
        state["active_task_id"] = record["task_id"]
        state["active_task_file"] = record["task_doc_path"]
        state["last_transition_at"] = _now_iso()
        _write_state(state)
    return _task_record_path(record["task_id"])


def pause_task(task_id: str, reason: str = "", *, reason_code: str | None = None, suggested_next_actions: list[str] | None = None) -> Path:
    record = _load_task_record(task_id)
    record["status"] = "paused_for_human"
    effective_code = reason_code or reason or "paused_for_human"
    record.update(_structured_block(effective_code, reason or effective_code))
    if suggested_next_actions is not None:
        record["suggested_next_actions"] = list(suggested_next_actions)
    record["updated_at"] = _now_iso()
    _save_task_record(record)
    state = _load_state()
    if state.get("active_task_id") == task_id:
        state["status"] = "paused_for_human"
        _apply_block_to_state(state, effective_code, reason or effective_code)
        state["last_transition_at"] = _now_iso()
        _write_state(state)
    return _task_record_path(task_id)


def resume_task(task_id: str) -> Path:
    record = _load_task_record(task_id)
    record["status"] = "ready"
    record["blocked_reason"] = ""
    record["blocked_reason_code"] = ""
    record["blocked_reason_detail"] = ""
    record["suggested_next_actions"] = []
    record["updated_at"] = _now_iso()
    _save_task_record(record)
    state = _load_state()
    state["active_task_id"] = task_id
    state["active_task_file"] = record["task_doc_path"]
    state["status"] = "context_ready"
    state["last_blocker_code"] = ""
    state["blocked_reason_code"] = ""
    state["blocked_reason_detail"] = ""
    state["suggested_next_actions"] = []
    state["last_transition_at"] = _now_iso()
    _write_state(state)
    return _task_record_path(task_id)


def prepare_plan_packet(run_id: str | None = None, task_id: str | None = None, task_file: str | None = None, handoff_file: str | None = None) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    LOOP_STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOOP_RUNS_DIR.mkdir(parents=True, exist_ok=True)

    state = _load_state()
    resolved_task_id = task_id or state.get("active_task_id", "")
    task_record = _load_task_record(resolved_task_id) if resolved_task_id else None
    if task_record is not None:
        task_record["status"] = "ready"
        task_record["updated_at"] = _now_iso()
        _save_task_record(task_record)

    resolved_run_id = run_id or _new_run_id()
    run_dir = _run_dir(resolved_run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    packet = build_context_packet(
        run_id=resolved_run_id,
        task_id=resolved_task_id or None,
        task_file=Path(task_file) if task_file else None,
        handoff_file=Path(handoff_file) if handoff_file else None,
        task_record=task_record,
    )
    packet_path = run_dir / PLANNER_PACKET_NAME
    write_json(packet_path, packet)

    state.update(
        {
            "status": "context_ready",
            "current_run_id": resolved_run_id,
            "active_task_id": resolved_task_id,
            "active_task_file": task_record["task_doc_path"] if task_record else packet.get("current_task", {}).get("path", ""),
            "last_handoff_file": packet.get("latest_handoff", {}).get("path", ""),
            "phase": packet.get("phase_hint", ""),
            "current_workspace_role": "",
            "current_workspace_path": "",
            "awaiting_output_file": "",
            "last_completed_role": "",
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    _write_active_objective(
        objective=(task_record or {}).get("objective", packet.get("current_focus", "")),
        task_type="",
        success_definition=(task_record or {}).get("success_criteria", []),
    )
    write_stage_checkpoint(
        run_dir=run_dir,
        run_id=resolved_run_id,
        task_id=resolved_task_id or "",
        runner_id=str(state.get("runner_id", "")),
        stage="plan_packet_prepared",
        state_status=str(state.get("status", "")),
        resume_hint="planner",
    )
    return packet_path


def _planner_template_for_task(task_record: dict[str, Any], packet: dict[str, Any], run_id: str) -> dict[str, Any]:
    workflow_kind = task_record.get("workflow_kind", "implementation_task")
    action_kind = "implementation" if workflow_kind == "implementation_task" else "experiment" if workflow_kind == "experiment_run" else "skill"
    action_name = ""
    if workflow_kind in TASK_TYPE_TO_SKILL:
        action_name = TASK_TYPE_TO_SKILL[workflow_kind]["skill"]
    elif workflow_kind == "artifact_repair":
        action_name = TASK_TYPE_TO_SKILL["artifact_repair"]["skill"]
        action_kind = "artifact_repair"
    elif workflow_kind == "implementation_task":
        action_name = "implementation-task"
    elif workflow_kind == "experiment_run":
        action_name = "experiment-run"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "task_id": task_record["task_id"],
        "phase": str(packet.get("phase_hint", "general_execution") or "general_execution"),
        "workflow_kind": workflow_kind,
        "task_type": workflow_kind if workflow_kind in TASK_TYPE_TO_SKILL else "",
        "objective": str(task_record.get("objective") or packet.get("current_focus") or "TODO: fill objective"),
        "preflight_required": True,
        "action": {
            "kind": action_kind,
            "name": action_name,
            "args": {
                **dict(TASK_TYPE_TO_SKILL.get(workflow_kind, {}).get("default_args", {})),
                **(
                    {
                        "command": str(task_record.get("experiment_command", "")),
                        "run_dir": str(task_record.get("experiment_run_dir", "")),
                        "config_path": str(task_record.get("experiment_config_path", "")),
                    }
                    if workflow_kind == "experiment_run"
                    else {}
                ),
            },
        },
        "success_criteria": list(task_record.get("success_criteria") or ["TODO: define success criteria"]),
        "fail_fast_conditions": ["TODO: list fail-fast conditions"],
        "review_focus": ["TODO: list review focus"],
        "risk_level": str(task_record.get("risk_level") or "medium"),
        "needs_human_before_execute": False,
        "allowed_write_paths": list(task_record.get("allowed_write_paths") or []),
        "required_checks": list(task_record.get("required_checks") or []),
        "experiment_required_artifacts": list(task_record.get("experiment_required_artifacts") or []),
        "linked_experiment_id": "",
        "autocontinue_eligible": workflow_kind in AUTOCONTINUE_WORKFLOW_KINDS,
        "template_note": "Edit this file into planner_decision.json after confirming args, checks, and write boundaries.",
    }


def prepare_planner_workspace(run_id: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    run_dir = _run_dir(run_id)
    packet_path = run_dir / PLANNER_PACKET_NAME
    if not packet_path.exists():
        raise GovernorError(f"planner packet not found for run `{run_id}`.")
    state = _load_state()
    if state.get("status") != "context_ready" or state.get("current_run_id") != run_id:
        raise GovernorError("planner workspace can only be prepared when state is context_ready for the same run.")

    output_path = run_dir / PLANNER_DECISION_NAME
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "role": "planner",
        "workspace_kind": "planner",
        "task_id": state.get("active_task_id", ""),
        "linked_experiment_id": "",
        "role_prompt_path": _relative_or_absolute(PLANNER_PROMPT_PATH),
        "window_template_path": _relative_or_absolute(PLANNER_WINDOW_TEMPLATE_PATH),
        "allowed_input_files": [
            _relative_or_absolute(packet_path),
            _relative_or_absolute(Path(ACTIVE_OBJECTIVE_PATH)),
            _relative_or_absolute(CURRENT_STATE_PATH),
        ],
        "required_output_file": PLANNER_DECISION_NAME,
        "required_output_path": _relative_or_absolute(output_path),
        "input_bundle": {
            "planner_input_packet": _relative_or_absolute(packet_path),
            "current_state": _relative_or_absolute(CURRENT_STATE_PATH),
            "active_objective": _relative_or_absolute(ACTIVE_OBJECTIVE_PATH),
        },
        "write_constraints": _base_write_constraints(PLANNER_DECISION_NAME, output_path),
        "next_step_instruction": f"Read only the files listed in `allowed_input_files`, then write `{PLANNER_DECISION_NAME}`.",
    }
    workspace_path = _write_workspace("planner", payload)
    state.update(
        {
            "status": "planner_workspace_ready",
            "current_workspace_role": "planner",
            "current_workspace_path": str(workspace_path),
            "awaiting_output_file": PLANNER_DECISION_NAME,
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    return workspace_path


def prepare_planner_decision_template(run_id: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    run_dir = _run_dir(run_id)
    packet_path = run_dir / PLANNER_PACKET_NAME
    if not packet_path.exists():
        raise GovernorError(f"planner packet not found for run `{run_id}`.")
    packet = load_json(packet_path)
    state = _load_state()
    task_id = state.get("active_task_id", "") or packet.get("task_id", "")
    if not task_id:
        raise GovernorError("planner template requires an active task_id in V2.")
    task_record = _load_task_record(task_id)
    template = _planner_template_for_task(task_record=task_record, packet=packet, run_id=run_id)
    output_path = run_dir / PLANNER_DECISION_TEMPLATE_NAME
    write_json(output_path, template)
    return output_path


def _prepare_executor_payload(decision_file: Path, workspace_kind: str, prompt_path: Path, template_path: Path) -> dict[str, Any]:
    decision = validate_planner_decision(load_json(decision_file)).data
    output_path = decision_file.parent / EXECUTION_RESULT_NAME
    template_output_path = decision_file.parent / EXECUTION_RESULT_TEMPLATE_NAME
    allowed_actions = [
        "Read planner_decision.json",
        "Operate only within the allowed write paths or experiment run scope",
        "Write execution_result.json using the provided schema/template",
    ]
    if workspace_kind == "executor":
        allowed_actions = [
            "Read planner_decision.json",
            "Call Governor CLI run-execution",
            "Inspect execution_result.json after command completion",
        ]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": decision["run_id"],
        "role": "executor",
        "workspace_kind": workspace_kind,
        "task_id": decision["task_id"],
        "linked_experiment_id": decision.get("linked_experiment_id", ""),
        "role_prompt_path": _relative_or_absolute(prompt_path),
        "window_template_path": _relative_or_absolute(template_path),
        "allowed_input_files": [
            _relative_or_absolute(decision_file),
            _relative_or_absolute(CURRENT_STATE_PATH),
        ],
        "required_output_file": EXECUTION_RESULT_NAME,
        "required_output_path": _relative_or_absolute(output_path),
        "input_bundle": {
            "planner_decision": _relative_or_absolute(decision_file),
            "current_state": _relative_or_absolute(CURRENT_STATE_PATH),
        },
        "write_constraints": _base_write_constraints(EXECUTION_RESULT_NAME, output_path),
        "allowed_actions": allowed_actions,
        "execution_result_template_path": _relative_or_absolute(template_output_path),
        "next_step_instruction": "Use the planner decision plus the execution_result template to complete this round.",
    }


def _build_execution_result_template(decision: dict[str, Any]) -> dict[str, Any]:
    write_set = list(decision.get("allowed_write_paths", [])) if decision["workflow_kind"] == "implementation_task" else []
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": decision["run_id"],
        "task_id": decision["task_id"],
        "linked_experiment_id": decision.get("linked_experiment_id", ""),
        "preflight": {
            "skill": "active-truth-calibration",
            "exit_code": 0,
            "status": "pass",
            "stdout_excerpt": "TODO",
            "stderr_excerpt": "",
            "stdout_json": {},
        },
        "action": {
            "kind": decision["action"]["kind"],
            "name": decision["action"]["name"],
            "command": "TODO",
            "args": decision["action"]["args"],
            "exit_code": 0,
            "stdout_excerpt": "",
            "stderr_excerpt": "",
            "stdout_json": {},
        },
        "artifacts": {},
        "machine_assessment": {
            "fail_fast": False,
            "completed_execution": True,
            "detected_conditions": [],
        },
        "write_set": write_set,
        "checks_run": list(decision.get("required_checks", [])),
        "checks_passed": [],
        "progress_delta": {
            "summary": "TODO: summarize what changed or what experiment was executed.",
            "fingerprint": "",
        },
        "template_note": "Fill this file after implementation/experiment execution if no Governor CLI run was used.",
    }


def prepare_executor_workspace(decision_path: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    decision_file = Path(decision_path)
    decision = validate_planner_decision(load_json(decision_file)).data
    run_id = decision["run_id"]
    state = _load_state()
    if state.get("current_run_id") != run_id:
        raise GovernorError("executor workspace run_id does not match current state.")
    if state.get("status") not in ("planner_workspace_ready", "planned"):
        raise GovernorError("executor workspace can only be prepared after planning starts.")
    if decision["workflow_kind"] not in ("truth_calibration", "governance_refresh", "results_closeout", "multilabel_readiness_audit", "artifact_repair"):
        raise GovernorError("prepare-executor-workspace only supports skill-like workflows.")

    payload = _prepare_executor_payload(decision_file, "executor", EXECUTOR_PROMPT_PATH, EXECUTOR_WINDOW_TEMPLATE_PATH)
    workspace_path = _write_workspace("executor", payload)
    state.update(
        {
            "status": "executor_workspace_ready",
            "current_workspace_role": "executor",
            "current_workspace_path": str(workspace_path),
            "awaiting_output_file": EXECUTION_RESULT_NAME,
            "last_completed_role": "planner",
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    return workspace_path


def prepare_implementation_workspace(decision_path: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    decision_file = Path(decision_path)
    decision = validate_planner_decision(load_json(decision_file)).data
    if decision["workflow_kind"] != "implementation_task":
        raise GovernorError("implementation workspace requires workflow_kind `implementation_task`.")
    payload = _prepare_executor_payload(decision_file, "implementation", IMPLEMENTATION_PROMPT_PATH, IMPLEMENTATION_WINDOW_TEMPLATE_PATH)
    write_json(decision_file.parent / EXECUTION_RESULT_TEMPLATE_NAME, _build_execution_result_template(decision))
    workspace_path = _write_workspace("executor", payload)
    state = _load_state()
    state.update(
        {
            "status": "implementation_workspace_ready",
            "current_workspace_role": "executor",
            "current_workspace_path": str(workspace_path),
            "awaiting_output_file": EXECUTION_RESULT_NAME,
            "last_completed_role": "planner",
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    return workspace_path


def prepare_experiment_workspace(decision_path: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    decision_file = Path(decision_path)
    decision = validate_planner_decision(load_json(decision_file)).data
    if decision["workflow_kind"] != "experiment_run":
        raise GovernorError("experiment workspace requires workflow_kind `experiment_run`.")
    payload = _prepare_executor_payload(decision_file, "experiment", EXPERIMENT_PROMPT_PATH, EXPERIMENT_WINDOW_TEMPLATE_PATH)
    write_json(decision_file.parent / EXECUTION_RESULT_TEMPLATE_NAME, _build_execution_result_template(decision))
    workspace_path = _write_workspace("executor", payload)
    state = _load_state()
    state.update(
        {
            "status": "experiment_workspace_ready",
            "current_workspace_role": "executor",
            "current_workspace_path": str(workspace_path),
            "awaiting_output_file": EXECUTION_RESULT_NAME,
            "last_completed_role": "planner",
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    return workspace_path


def prepare_reviewer_workspace(execution_result_path: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    execution_file = Path(execution_result_path)
    execution = validate_execution_result(load_json(execution_file)).data
    run_id = execution["run_id"]
    decision_file = execution_file.parent / PLANNER_DECISION_NAME
    if not decision_file.exists():
        raise GovernorError("reviewer workspace requires planner_decision.json in the same run directory.")
    validate_planner_decision(load_json(decision_file))
    state = _load_state()
    if state.get("current_run_id") != run_id:
        raise GovernorError("reviewer workspace run_id does not match current state.")
    if state.get("status") not in (
        "executed",
        "reviewer_workspace_ready",
        "implementation_workspace_ready",
        "experiment_workspace_ready",
    ):
        raise GovernorError("reviewer workspace can only be prepared after execution.")

    output_path = execution_file.parent / REVIEW_VERDICT_NAME
    decision = validate_planner_decision(load_json(decision_file)).data
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "role": "reviewer",
        "workspace_kind": "reviewer",
        "task_id": decision["task_id"],
        "linked_experiment_id": decision.get("linked_experiment_id", ""),
        "role_prompt_path": _relative_or_absolute(REVIEWER_PROMPT_PATH),
        "window_template_path": _relative_or_absolute(REVIEWER_WINDOW_TEMPLATE_PATH),
        "allowed_input_files": [
            _relative_or_absolute(decision_file),
            _relative_or_absolute(execution_file),
            _relative_or_absolute(CURRENT_STATE_PATH),
        ],
        "required_output_file": REVIEW_VERDICT_NAME,
        "required_output_path": _relative_or_absolute(output_path),
        "input_bundle": {
            "planner_decision": _relative_or_absolute(decision_file),
            "execution_result": _relative_or_absolute(execution_file),
            "current_state": _relative_or_absolute(CURRENT_STATE_PATH),
        },
        "write_constraints": _base_write_constraints(REVIEW_VERDICT_NAME, output_path),
        "review_policy": [
            "Do not read planner_input_packet.json.",
            "Do not read historical loop_runs unless explicitly included.",
            "Base the verdict only on planner_decision, execution_result, and current_state.",
        ],
        "next_step_instruction": f"Read only the decision, execution result, and current state, then write `{REVIEW_VERDICT_NAME}`.",
    }
    workspace_path = _write_workspace("reviewer", payload)
    state.update(
        {
            "status": "reviewer_workspace_ready",
            "current_workspace_role": "reviewer",
            "current_workspace_path": str(workspace_path),
            "awaiting_output_file": REVIEW_VERDICT_NAME,
            "last_completed_role": "executor",
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    write_stage_checkpoint(
        run_dir=execution_file.parent,
        run_id=run_id,
        task_id=decision["task_id"],
        runner_id=str(state.get("runner_id", "")),
        stage="review_started",
        state_status=str(state.get("status", "")),
        resume_hint="reviewer",
    )
    return workspace_path


def prepare_review_verdict_template(execution_result_path: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    execution_file = Path(execution_result_path)
    execution = validate_execution_result(load_json(execution_file)).data
    run_dir = execution_file.parent
    decision = validate_planner_decision(load_json(run_dir / PLANNER_DECISION_NAME)).data
    machine = execution["machine_assessment"]
    issues = list(machine.get("detected_conditions", []))
    action_exit_code = int(execution["action"]["exit_code"])
    required_checks = list(decision.get("required_checks", []))
    checks_run = list(execution.get("checks_run", []))
    checks_passed = list(execution.get("checks_passed", []))
    missing_checks = [item for item in required_checks if item not in checks_run]
    failed_checks = [item for item in required_checks if item not in checks_passed]
    if action_exit_code != 0 and not issues:
        issues.append(f"action_exit_code_{action_exit_code}")
    if missing_checks:
        issues.extend(f"missing_required_check:{item}" for item in missing_checks)
    if failed_checks:
        issues.extend(f"failed_required_check:{item}" for item in failed_checks)
    objective_met = not bool(machine.get("fail_fast", False)) and bool(machine.get("completed_execution", False))
    if decision["workflow_kind"] == "implementation_task" and failed_checks and bool(load_policy().get("implementation_require_all_checks_pass", True)):
        objective_met = False
    verdict = "approve" if objective_met else "revise"
    next_mode = "complete" if objective_met and decision["workflow_kind"] in ("results_closeout", "artifact_repair") else "continue" if objective_met else "replan"
    if objective_met and decision["workflow_kind"] == "truth_calibration" and isinstance(execution.get("decision_payload", {}), dict) and execution.get("decision_payload"):
        next_mode = "complete"
    next_objective = (
        f"Continue task `{decision['task_id']}` after successful `{decision['workflow_kind']}`."
        if objective_met
        else f"Fix the detected execution issues for `{decision['workflow_kind']}` and retry."
    )
    template = {
        "schema_version": SCHEMA_VERSION,
        "run_id": execution["run_id"],
        "task_id": decision["task_id"],
        "linked_experiment_id": decision.get("linked_experiment_id", ""),
        "verdict": verdict,
        "objective_met": objective_met,
        "needs_human": False,
        "drift_detected": False,
        "issues": issues,
        "recommended_next_mode": next_mode,
        "next_objective": next_objective,
        "evidence": {
            "write_set": list(execution.get("write_set", [])),
            "checks_run": list(execution.get("checks_run", [])),
            "checks_passed": list(execution.get("checks_passed", [])),
            "detected_conditions": list(machine.get("detected_conditions", [])),
        },
        "decision_payload": dict(execution.get("decision_payload", {})),
        "template_note": "Edit this file if reviewer judgment differs from the auto-drafted suggestion.",
    }
    output_path = run_dir / REVIEW_VERDICT_TEMPLATE_NAME
    write_json(output_path, template)
    return output_path


def _execution_from_skill(decision: dict[str, Any]) -> dict[str, Any]:
    preflight_result = run_skill("active-truth-calibration", {"format": "json"})
    preflight_json = parse_json_output(preflight_result.stdout)
    preflight_status = "pass" if preflight_result.exit_code == 0 else "fail_fast"

    if decision["workflow_kind"] == "truth_calibration":
        action_result = preflight_result
        action_stdout_json = preflight_json
        action_payload = _record_command("skill", action_result, action_stdout_json)
        action_payload["reused_preflight_result"] = True
    else:
        action = decision["action"]
        merged_args = _merge_action_args(decision["workflow_kind"], action["kind"], action["name"], action["args"])
        action_result = run_skill(action["name"], merged_args)
        action_stdout_json = parse_json_output(action_result.stdout)
        kind = "artifact_repair" if decision["workflow_kind"] == "artifact_repair" else "skill"
        action_payload = _record_command(kind, action_result, action_stdout_json)

    task_artifacts = collect_task_artifacts(
        task_type=decision["workflow_kind"],
        action_args=action_payload["args"],
        stdout_json=action_stdout_json,
    )
    machine_assessment = _build_machine_assessment(
        workflow_kind=decision["workflow_kind"],
        preflight_result=preflight_result,
        action_result=action_result,
        action_stdout_json=action_stdout_json,
        task_artifacts=task_artifacts,
    )
    decision_payload = (
        _decision_payload_for_truth_calibration(decision, stdout_json=action_stdout_json)
        if decision["workflow_kind"] == "truth_calibration"
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": decision["run_id"],
        "task_id": decision["task_id"],
        "linked_experiment_id": decision.get("linked_experiment_id", ""),
        "preflight": {
            "skill": preflight_result.skill,
            "exit_code": preflight_result.exit_code,
            "status": preflight_status,
            "stdout_excerpt": text_excerpt(preflight_result.stdout),
            "stderr_excerpt": text_excerpt(preflight_result.stderr),
            "stdout_json": preflight_json,
        },
        "action": action_payload,
        "artifacts": task_artifacts,
        "machine_assessment": machine_assessment,
        "write_set": [],
        "checks_run": [],
        "checks_passed": [],
        "decision_payload": decision_payload,
        "progress_delta": {
            "summary": f"Executed `{decision['workflow_kind']}` via `{action_payload['name']}`.",
            "fingerprint": f"{decision['workflow_kind']}|{action_payload['name']}|{action_payload['exit_code']}",
        },
    }


def run_execution(decision_path: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    decision_file = Path(decision_path)
    decision = validate_planner_decision(load_json(decision_file)).data
    run_id = decision["run_id"]
    run_dir = decision_file.parent
    if run_dir.name != run_id:
        raise GovernorError("planner decision file must live under loop_runs/<run_id>/")

    state = _load_state()
    if state.get("current_run_id") != run_id:
        raise GovernorError("execution run_id does not match current state.")
    if state.get("status") not in (
        "executor_workspace_ready",
        "implementation_workspace_ready",
        "experiment_workspace_ready",
        "planner_workspace_ready",
        "context_ready",
    ):
        raise GovernorError("run-execution is only allowed after preparing the executor workspace.")
    if decision["workflow_kind"] not in (
        "truth_calibration",
        "governance_refresh",
        "results_closeout",
        "multilabel_readiness_audit",
        "artifact_repair",
        "implementation_task",
        "experiment_run",
    ):
        raise GovernorError("run-execution only supports skill-like workflows, implementation_task, and experiment_run in V2.5.")

    state.update(
        {
            "status": "planned",
            "current_run_id": run_id,
            "phase": decision["phase"],
            "active_task_id": decision["task_id"],
            "active_experiment_id": decision.get("linked_experiment_id", ""),
            "last_completed_role": "planner",
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)

    all_gate_reasons = _gate_planner_decision(decision) + _gate_action_assets(decision)
    if all_gate_reasons:
        state.update({"status": "paused_for_human", "last_transition_at": _now_iso()})
        _apply_block_to_state(state, "planner_gate", "; ".join(all_gate_reasons))
        _write_state(state)
        task_record = _load_task_record(decision["task_id"])
        task_record["status"] = "paused_for_human"
        _apply_block_to_task(task_record, "planner_gate", "; ".join(all_gate_reasons))
        task_record["updated_at"] = _now_iso()
        _save_task_record(task_record)
        raise GovernorError("execution blocked by governor gate: " + "; ".join(all_gate_reasons))

    state.update({"status": "gated", "last_transition_at": _now_iso()})
    _write_state(state)
    write_stage_checkpoint(
        run_dir=run_dir,
        run_id=run_id,
        task_id=decision["task_id"],
        runner_id=str(state.get("runner_id", "")),
        stage="execution_started",
        state_status=str(state.get("status", "")),
        resume_hint="execution",
    )

    if decision["workflow_kind"] == "implementation_task":
        execution_payload = execute_implementation(decision, policy=load_policy(), run_dir=run_dir)
    elif decision["workflow_kind"] == "experiment_run":
        execution_payload = execute_experiment(decision, policy=load_policy(), run_dir=run_dir)
    else:
        execution_payload = _execution_from_skill(decision)
    validate_execution_result(execution_payload)
    result_path = run_dir / EXECUTION_RESULT_NAME
    write_json(result_path, execution_payload)

    state["round_count"] = int(state.get("round_count", 0)) + 1
    state.update(
        {
            "status": "executed",
            "current_workspace_role": "",
            "current_workspace_path": "",
            "awaiting_output_file": "",
            "last_completed_role": "executor",
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    _write_active_objective(
        objective=decision["objective"],
        task_type=decision["task_type"],
        success_definition=decision["success_criteria"],
    )
    write_stage_checkpoint(
        run_dir=run_dir,
        run_id=run_id,
        task_id=decision["task_id"],
        runner_id=str(state.get("runner_id", "")),
        stage="execution_finished",
        state_status=str(state.get("status", "")),
        resume_hint="reviewer",
    )
    return result_path


def sync_experiment_from_run(task_id: str, run_dir: str, status: str = "candidate", config_path: str = "") -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    if status not in ALLOWED_EXPERIMENT_STATUSES:
        raise GovernorError(f"invalid experiment status `{status}`.")
    task_record = _load_task_record(task_id)
    draft = build_experiment_registry_draft(_resolve_repo_path(run_dir), task_id=task_id, config_path=config_path or None)
    draft["status"] = status
    _save_experiment_record(draft)
    linked = list(task_record.get("linked_experiments", []))
    if draft["experiment_id"] not in linked:
        linked.append(draft["experiment_id"])
        task_record["linked_experiments"] = linked
        task_record["updated_at"] = _now_iso()
        _save_task_record(task_record)
    return _experiment_record_path(draft["experiment_id"])


def _update_task_from_verdict(task_record: dict[str, Any], decision: dict[str, Any], execution: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    workflow_kind = decision["workflow_kind"]
    task_id = str(task_record.get("task_id", ""))
    is_trial_task = "autopilot-trial" in task_id
    evidence = _review_evidence(execution, verdict)
    if verdict["verdict"] == "escalate" or verdict["needs_human"] or verdict["drift_detected"]:
        task_record["status"] = "paused_for_human"
        _apply_block_to_task(task_record, "review_escalated", "review_escalated", evidence=evidence)
    elif workflow_kind == "implementation_task":
        checks_match = bool(execution["checks_run"]) and execution["checks_run"] == execution["checks_passed"]
        if verdict["verdict"] == "approve" and checks_match:
            task_record["status"] = "completed" if is_trial_task else "evaluating" if decision.get("linked_experiment_id") else "ready"
            task_record["blocked_reason"] = ""
            task_record["blocked_reason_code"] = ""
            task_record["blocked_reason_detail"] = ""
            task_record["suggested_next_actions"] = []
        else:
            task_record["status"] = "paused_for_human"
            issues = list(verdict.get("issues", []))
            reason_code = _canonical_reason_code(issues[0]) if issues else "implementation_required_checks_failed"
            _apply_block_to_task(task_record, reason_code, "; ".join(issues) or reason_code, evidence=evidence)
    elif workflow_kind == "experiment_run":
        if verdict["verdict"] == "approve":
            task_record["status"] = "evaluating"
            task_record["blocked_reason"] = ""
            task_record["blocked_reason_code"] = ""
            task_record["blocked_reason_detail"] = ""
            task_record["suggested_next_actions"] = []
        elif verdict["verdict"] == "revise":
            task_record["status"] = "blocked"
            issues = list(verdict.get("issues", []))
            _apply_block_to_task(
                task_record,
                _canonical_reason_code(issues[0]) if issues else "review_escalated",
                "; ".join(issues),
                evidence=evidence,
            )
    else:
        if verdict["recommended_next_mode"] == "complete" or (
            verdict["verdict"] == "approve"
            and str(decision.get("workflow_kind", "")) == "truth_calibration"
            and isinstance(verdict.get("decision_payload", execution.get("decision_payload", {})), dict)
            and (verdict.get("decision_payload") or execution.get("decision_payload"))
        ):
            task_record["status"] = "completed"
            task_record["blocked_reason"] = ""
            task_record["blocked_reason_code"] = ""
            task_record["blocked_reason_detail"] = ""
            task_record["suggested_next_actions"] = []
        elif verdict["verdict"] == "approve" and is_trial_task:
            task_record["status"] = "completed"
            task_record["blocked_reason"] = ""
            task_record["blocked_reason_code"] = ""
            task_record["blocked_reason_detail"] = ""
            task_record["suggested_next_actions"] = []
        elif verdict["recommended_next_mode"] == "pause_for_human":
            task_record["status"] = "paused_for_human"
            issues = list(verdict.get("issues", []))
            _apply_block_to_task(
                task_record,
                _canonical_reason_code(issues[0]) if issues else "paused_for_human",
                "; ".join(issues),
                evidence=evidence,
            )
        else:
            task_record["status"] = "ready"
            task_record["blocked_reason"] = ""
            task_record["blocked_reason_code"] = ""
            task_record["blocked_reason_detail"] = ""
            task_record["suggested_next_actions"] = []
    task_record["last_run_id"] = decision["run_id"]
    task_record["decision_payload"] = dict(verdict.get("decision_payload", execution.get("decision_payload", {})))
    task_record["updated_at"] = _now_iso()
    return task_record


def _update_experiment_from_verdict(experiment_id: str, decision: dict[str, Any], execution: dict[str, Any], verdict: dict[str, Any]) -> None:
    record = _load_experiment_record(experiment_id)
    record["review_verdict"] = verdict["verdict"]
    record["last_verified_at"] = _now_iso()
    if isinstance(verdict.get("workflow_signal"), dict):
        record["workflow_signal"] = dict(verdict.get("workflow_signal", {}))
    if decision["workflow_kind"] == "artifact_repair":
        record["closeout_status"] = "repaired" if verdict["verdict"] == "approve" else "failed"
    elif decision["workflow_kind"] == "results_closeout":
        record["closeout_status"] = "passed" if verdict["verdict"] == "approve" else "failed"
    elif decision["workflow_kind"] == "experiment_run":
        if verdict["verdict"] == "approve":
            record["status"] = str(record.get("status") or "candidate")
            record["closeout_status"] = str(execution.get("artifacts", {}).get("closeout_status", record.get("closeout_status", "ready")) or "ready")
        else:
            record["closeout_status"] = "failed"
    _save_experiment_record(record)


def _derive_workflow_signal(task_record: dict[str, Any], decision: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    signal = {
        "enter_extended_staging": False,
        "enter_promotion_candidate": False,
        "runtime_blocker": verdict["verdict"] != "approve" or verdict["needs_human"] or verdict["drift_detected"],
        "additional_seed_required": False,
    }
    if str(decision.get("workflow_kind", "")) != "results_closeout":
        return signal
    task_id = str(task_record.get("task_id", ""))
    if task_id.endswith("promotion-readiness-review") and verdict["verdict"] == "approve":
        signal["enter_extended_staging"] = True
    if task_id.endswith("extended-real-case-closeout-decision") and verdict["verdict"] == "approve":
        signal["enter_promotion_candidate"] = True
    return signal


def advance_review(verdict_path: str) -> Path:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    verdict_file = Path(verdict_path)
    verdict = validate_review_verdict(load_json(verdict_file)).data
    run_dir = verdict_file.parent
    run_id = verdict["run_id"]

    decision = validate_planner_decision(load_json(run_dir / PLANNER_DECISION_NAME)).data
    execution = validate_execution_result(load_json(run_dir / EXECUTION_RESULT_NAME)).data
    if decision["run_id"] != run_id or execution["run_id"] != run_id:
        raise SchemaValidationError("planner/execution/review run_id mismatch.")

    state = _load_state()
    policy = load_policy()
    if state.get("current_run_id") != run_id:
        raise GovernorError("review run_id does not match current state.")
    if state.get("status") not in ("reviewer_workspace_ready", "executed"):
        raise GovernorError("advance-review is only allowed after preparing the reviewer workspace.")

    fingerprint = _fingerprint_from_payload(execution)
    write_stage_checkpoint(
        run_dir=run_dir,
        run_id=run_id,
        task_id=decision["task_id"],
        runner_id=str(state.get("runner_id", "")),
        stage="review_finished",
        state_status=str(state.get("status", "")),
        resume_hint="state_commit",
    )
    no_progress = (not verdict["objective_met"]) or (fingerprint and fingerprint == state.get("last_progress_fingerprint", ""))
    state["consecutive_no_progress"] = int(state.get("consecutive_no_progress", 0)) + 1 if no_progress else 0

    next_mode = verdict["recommended_next_mode"]
    task_record = _load_task_record(decision["task_id"])
    verdict["workflow_signal"] = _derive_workflow_signal(task_record, decision, verdict)
    write_json(verdict_file, validate_review_verdict(verdict).data)
    projected_task_record = _update_task_from_verdict(dict(task_record), decision, execution, verdict)
    projected_task_record["workflow_signal"] = dict(verdict.get("workflow_signal", {}))
    evidence = _review_evidence(execution, verdict)
    if projected_task_record["status"] == "completed":
        next_mode = "complete"
    else:
        if verdict["verdict"] == "escalate" or verdict["needs_human"] or verdict["drift_detected"]:
            next_mode = "pause_for_human"
        elif bool(policy.get("pause_on_review_revise", True)) and verdict["verdict"] == "revise":
            next_mode = "pause_for_human"
        elif state["consecutive_no_progress"] >= int(policy.get("max_consecutive_no_progress", 2)):
            next_mode = "pause_for_human"
            verdict["issues"] = list(verdict.get("issues", [])) + ["two_rounds_no_progress"]
            projected_task_record["status"] = "paused_for_human"
            _apply_block_to_task(
                projected_task_record,
                "two_rounds_no_progress",
                "; ".join(verdict["issues"]),
                evidence=evidence,
            )

    _save_task_record(projected_task_record)

    experiment_id = decision.get("linked_experiment_id", "") or verdict.get("linked_experiment_id", "")
    if experiment_id:
        _update_experiment_from_verdict(experiment_id, decision, execution, verdict)

    if next_mode == "pause_for_human":
        state["status"] = "paused_for_human"
        state["auto_rounds_since_human"] = 0
        issues = list(verdict.get("issues", []))
        _apply_block_to_state(
            state,
            _canonical_reason_code(issues[0]) if issues else "paused_for_human",
            "; ".join(issues),
            evidence=evidence,
        )
    elif next_mode == "complete":
        state["status"] = "completed"
        state["consecutive_no_progress"] = 0
        state["auto_rounds_since_human"] = 0
        state["last_blocker_code"] = ""
        state["blocked_reason_code"] = ""
        state["blocked_reason_detail"] = ""
        state["suggested_next_actions"] = []
    else:
        state["status"] = "context_ready"
        state["auto_rounds_since_human"] = int(state.get("auto_rounds_since_human", 0)) + 1 if decision["autocontinue_eligible"] and decision["workflow_kind"] in AUTOCONTINUE_WORKFLOW_KINDS and decision["risk_level"] == "low" else 0
        state["last_blocker_code"] = ""
        state["blocked_reason_code"] = ""
        state["blocked_reason_detail"] = ""
        state["suggested_next_actions"] = []

    state.update(
        {
            "current_run_id": run_id,
            "phase": decision["phase"],
            "active_task_id": decision["task_id"],
            "active_experiment_id": experiment_id,
            "last_completed_role": "reviewer",
            "current_workspace_role": "",
            "current_workspace_path": "",
            "awaiting_output_file": "",
            "last_progress_fingerprint": fingerprint,
            "last_transition_at": _now_iso(),
        }
    )
    _write_state(state)
    _write_active_objective(
        objective=verdict["next_objective"],
        task_type=decision["task_type"],
        success_definition=decision["success_criteria"],
    )
    write_stage_checkpoint(
        run_dir=run_dir,
        run_id=run_id,
        task_id=decision["task_id"],
        runner_id=str(state.get("runner_id", "")),
        stage="state_committed",
        state_status=str(state.get("status", "")),
        resume_hint="completed",
    )

    summary_path = run_dir / ROUND_SUMMARY_NAME
    summary_path.write_text(_render_round_summary(decision, execution, verdict), encoding="utf-8")
    return summary_path


def prepare_handoff_template(task_id: str) -> Path:
    task_record = _load_task_record(task_id)
    state = _load_state()
    output_path = HANDOFF_DIR / f"{task_id}-{HANDOFF_TEMPLATE_NAME}"
    output_path.write_text(
        "\n".join(
            [
                f"# Handoff: {task_record['title']}",
                "",
                f"- task_id: `{task_id}`",
                f"- current_status: `{task_record['status']}`",
                f"- last_run_id: `{task_record.get('last_run_id', '')}`",
                f"- blocked_reason: {task_record.get('blocked_reason', '') or 'n/a'}",
                f"- loop_state_status: `{state['status']}`",
                "",
                "## Next Step",
                f"- {load_json(ACTIVE_OBJECTIVE_PATH).get('objective', 'TODO')}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def prepare_report_template(task_id: str, experiment_id: str) -> Path:
    task_record = _load_task_record(task_id)
    experiment = _load_experiment_record(experiment_id)
    output_path = REPORTS_DIR / f"{task_id}-{REPORT_TEMPLATE_NAME}"
    output_path.write_text(
        "\n".join(
            [
                f"# Report Template: {task_record['title']}",
                "",
                f"- task_id: `{task_id}`",
                f"- experiment_id: `{experiment_id}`",
                f"- run_dir: `{experiment['run_dir']}`",
                f"- status: `{experiment['status']}`",
                f"- closeout_status: `{experiment['closeout_status']}`",
                f"- review_verdict: `{experiment.get('review_verdict', '')}`",
                "",
                "## Registry Snapshot",
                f"- variant: `{experiment['variant']}`",
                f"- seed: `{experiment['seed']}`",
                f"- best_val_l3_macro_f1: `{experiment.get('best_val_l3_macro_f1')}`",
                f"- best_val_multilabel_micro_f1: `{experiment.get('best_val_multilabel_micro_f1')}`",
                f"- mean_gates: `{experiment.get('mean_gates', {})}`",
                f"- gate_health: `{experiment.get('gate_health', {})}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path
