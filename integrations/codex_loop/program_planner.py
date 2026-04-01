from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import (
    BEST_KNOWN_METRICS_PATH,
    DECISION_MEMORY_PATH,
    DEFAULT_INTERVENTION_POLICY,
    EXPERIMENT_REGISTRY_DIR,
    MILESTONES_PATH,
    PROGRAM_BUDGET_STATE_PATH,
    PROGRAM_HANDOFF_PATH,
    REPORTS_DIR,
)
from integrations.codex_loop.events import append_event
from integrations.codex_loop.governor import create_task, get_runtime_policy, get_task_record, list_task_records, save_task_record
from integrations.codex_loop.regression_sentinel import evaluate_regression
from integrations.codex_loop.schemas import (
    SchemaValidationError,
    default_best_known_metrics,
    default_program_budget_state,
    default_program_handoff,
    default_milestones_state,
    default_program_state,
    ensure_parent,
    ensure_runtime_state_files,
    load_json,
    validate_best_known_metrics,
    validate_experiment_record,
    validate_milestones_state,
    validate_program_budget_state,
    validate_program_handoff,
    validate_program_state,
    write_json,
)
from integrations.codex_loop.task_templates import build_multilabel_phase2_placeholder, build_multilabel_phase3_placeholder
from integrations.codex_loop.workflow_registry import (
    WORKFLOW_TEMPLATES,
    active_workflow_instance,
    create_workflow_instance,
    load_program_state,
    save_program_state,
    show_workflow_status,
    workflow_template,
)


PRIMARY_GOAL = "multilabel_gate_load_balance_promotion"

DEFAULT_DECISIONS = [
    {
        "decision_id": "multilabel-mainline-gate-load-balance",
        "topic": "multilabel_mainline_candidate",
        "topic_kind": "lane_choice",
        "chosen_option": "gate_load_balance",
        "rejected_options": ["gate_entropy"],
        "evidence_ids": [
            "2026-04-01-gate-load-balance-promotion-candidate-decision",
        ],
        "confidence": 0.9,
        "supersedes": [],
        "decision_status": "active",
        "next_action_hint": "none",
        "blocks_workflows": ["gate_entropy_parallel_lane"],
    },
    {
        "decision_id": "multilabel-no-restore-all",
        "topic": "restore_all_modalities",
        "topic_kind": "runtime_scope",
        "chosen_option": "do_not_restore_all",
        "rejected_options": ["restore_all"],
        "evidence_ids": [
            "2026-04-01-gate-load-balance-promotion-candidate-decision",
        ],
        "confidence": 0.95,
        "supersedes": [],
        "decision_status": "active",
        "next_action_hint": "none",
        "blocks_workflows": ["restore_all_modalities"],
    },
    {
        "decision_id": "multilabel-no-selector-yet",
        "topic": "multilabel_inference_selector",
        "topic_kind": "inference_protocol",
        "chosen_option": "defer_selector",
        "rejected_options": ["implement_is_multilabel_selector_now"],
        "evidence_ids": [
            "2026-04-01-multilabel-inference-protocol-design",
        ],
        "confidence": 0.7,
        "supersedes": [],
        "decision_status": "tentative",
        "next_action_hint": "multilabel_inference_protocol_decision",
        "blocks_workflows": [],
    },
    {
        "decision_id": "multilabel-experiment-eval-mainline",
        "topic": "multilabel_runtime_scope",
        "topic_kind": "runtime_scope",
        "chosen_option": "experiment_and_evaluation_only",
        "rejected_options": ["final_inference_protocol_complete"],
        "evidence_ids": [
            "2026-04-01-gate-load-balance-promotion-candidate-decision",
        ],
        "confidence": 0.8,
        "supersedes": [],
        "decision_status": "active",
        "next_action_hint": "multilabel_inference_protocol_decision",
        "blocks_workflows": [],
    },
]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _milestone_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "milestone_id": "gate_load_balance_validation_complete",
            "title": "Gate Load Balance Validation Complete",
            "entry_conditions": ["real_case_closeout_complete", "higher_budget_closeout_complete", "second_seed_closeout_complete"],
            "success_conditions": ["second_seed_closeout_complete"],
            "linked_workflow_template": "gate_load_balance_promotion",
            "linked_topic": "multilabel_mainline_candidate",
            "auto_resume_allowed": False,
        },
        {
            "milestone_id": "gate_load_balance_promotion_candidate",
            "title": "Gate Load Balance Promotion Candidate",
            "entry_conditions": ["gate_load_balance_validation_complete"],
            "success_conditions": ["promotion_candidate_decision_complete"],
            "linked_workflow_template": "gate_load_balance_promotion",
            "linked_topic": "promotion_policy",
            "auto_resume_allowed": False,
        },
        {
            "milestone_id": "multilabel_inference_protocol_decision_ready",
            "title": "Multilabel Inference Protocol Decision Ready",
            "entry_conditions": ["gate_load_balance_promotion_candidate"],
            "success_conditions": ["decision_memory_updated"],
            "linked_workflow_template": "multilabel_inference_protocol_decision",
            "linked_topic": "multilabel_inference_selector",
            "auto_resume_allowed": True,
        },
        {
            "milestone_id": "promotion_candidate_followup_pending",
            "title": "Promotion Candidate Follow-up Pending",
            "entry_conditions": ["gate_load_balance_promotion_candidate"],
            "success_conditions": ["followup_workflow_selected"],
            "linked_workflow_template": "promotion_candidate_followup",
            "linked_topic": "promotion_policy",
            "auto_resume_allowed": True,
        },
        {
            "milestone_id": "dual_output_implementation_plan_ready",
            "title": "Dual Output Implementation Plan Ready",
            "entry_conditions": ["promotion_candidate_followup_pending"],
            "success_conditions": ["dual_output_plan_decided"],
            "linked_workflow_template": "dual_output_implementation_plan",
            "linked_topic": "dual_output_implementation_plan",
            "auto_resume_allowed": True,
        },
    ]


def _load_milestones_state() -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    return validate_milestones_state(load_json(MILESTONES_PATH)).data


def _write_milestones_state(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_milestones_state(payload).data
    write_json(MILESTONES_PATH, validated)
    return validated


def _read_decision_lines() -> list[dict[str, Any]]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    entries: list[dict[str, Any]] = []
    try:
        lines = DECISION_MEMORY_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return entries
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _append_decision(entry: dict[str, Any]) -> None:
    payload = {
        **entry,
        "recorded_at": entry.get("recorded_at") or _now_iso(),
        "decision_status": str(entry.get("decision_status", "active")),
        "topic_kind": str(entry.get("topic_kind", "")),
        "next_action_hint": str(entry.get("next_action_hint", "")),
        "blocks_workflows": list(entry.get("blocks_workflows", [])),
    }
    with DECISION_MEMORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_decision_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ensure_parent(DECISION_MEMORY_PATH)
    with DECISION_MEMORY_PATH.open("w", encoding="utf-8") as handle:
        for entry in entries:
            payload = dict(entry)
            payload["recorded_at"] = str(payload.get("recorded_at", "")) or _now_iso()
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return entries


def _normalize_decision_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    defaults_by_id = {str(item["decision_id"]): item for item in DEFAULT_DECISIONS}
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in entries:
        decision_id = str(entry.get("decision_id", "")).strip()
        merged = dict(defaults_by_id.get(decision_id, {}))
        merged.update(entry)
        merged["decision_id"] = decision_id or str(merged.get("decision_id", ""))
        merged["decision_status"] = str(merged.get("decision_status", "active"))
        merged["topic_kind"] = str(merged.get("topic_kind", ""))
        merged["next_action_hint"] = str(merged.get("next_action_hint", ""))
        merged["blocks_workflows"] = list(merged.get("blocks_workflows", []))
        merged["recorded_at"] = str(merged.get("recorded_at", "")) or _now_iso()
        normalized.append(merged)
        if merged["decision_id"]:
            seen_ids.add(merged["decision_id"])
    for item in DEFAULT_DECISIONS:
        if item["decision_id"] not in seen_ids:
            merged = dict(item)
            merged["recorded_at"] = str(merged.get("recorded_at", "")) or _now_iso()
            normalized.append(merged)
    return normalized


def ensure_decision_memory() -> list[dict[str, Any]]:
    existing = _read_decision_lines()
    normalized = _normalize_decision_entries(existing)
    ensure_parent(DECISION_MEMORY_PATH)
    with DECISION_MEMORY_PATH.open("w", encoding="utf-8") as handle:
        for entry in normalized:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return normalized


def _upsert_decision(entry: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = ensure_decision_memory()
    topic = str(entry.get("topic", "")).strip()
    decision_id = str(entry.get("decision_id", "")).strip()
    if not topic or not decision_id:
        return decisions
    normalized: list[dict[str, Any]] = []
    already_present = False
    for item in decisions:
        current = dict(item)
        if str(current.get("decision_id", "")) == decision_id:
            current.update(entry)
            current["recorded_at"] = str(current.get("recorded_at", "")) or _now_iso()
            already_present = True
        elif str(current.get("topic", "")) == topic and str(current.get("decision_status", "")) == "active":
            current["decision_status"] = "superseded"
        normalized.append(current)
    if not already_present:
        payload = dict(entry)
        payload["recorded_at"] = str(payload.get("recorded_at", "")) or _now_iso()
        normalized.append(payload)
    return _write_decision_entries(normalized)


def show_decisions() -> dict[str, Any]:
    decisions = ensure_decision_memory()
    return {
        "decision_count": len(decisions),
        "decisions": decisions,
    }


def _load_budget_state() -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    try:
        return validate_program_budget_state(load_json(PROGRAM_BUDGET_STATE_PATH)).data
    except (json.JSONDecodeError, OSError, SchemaValidationError, ValueError):
        return validate_program_budget_state(default_program_budget_state()).data


def _write_budget_state(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_program_budget_state(payload).data
    write_json(PROGRAM_BUDGET_STATE_PATH, validated)
    return validated


def _load_best_known_metrics() -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    try:
        return validate_best_known_metrics(load_json(BEST_KNOWN_METRICS_PATH)).data
    except (json.JSONDecodeError, OSError, SchemaValidationError, ValueError):
        return validate_best_known_metrics(default_best_known_metrics()).data


def _write_best_known_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_best_known_metrics(payload).data
    write_json(BEST_KNOWN_METRICS_PATH, validated)
    return validated


def _load_program_handoff() -> dict[str, Any]:
    ensure_runtime_state_files(DEFAULT_INTERVENTION_POLICY)
    try:
        return validate_program_handoff(load_json(PROGRAM_HANDOFF_PATH)).data
    except (json.JSONDecodeError, OSError, SchemaValidationError, ValueError):
        return validate_program_handoff(default_program_handoff()).data


def _write_program_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_program_handoff(payload).data
    write_json(PROGRAM_HANDOFF_PATH, validated)
    return validated


def _write_program_summary_report(handoff: dict[str, Any]) -> Path:
    report_dir = REPORTS_DIR / "program"
    report_dir.mkdir(parents=True, exist_ok=True)
    date_prefix = datetime.now().astimezone().date().isoformat()
    report_path = report_dir / f"{date_prefix}-program-summary.md"
    best_known = handoff.get("best_known_metrics_snapshot", {}) if isinstance(handoff.get("best_known_metrics_snapshot"), dict) else {}
    lines = [
        "# Program Summary",
        "",
        f"- primary_goal: `{handoff.get('primary_goal', '')}`",
        f"- active_lane: `{handoff.get('active_lane', '')}`",
        f"- active_milestone: `{handoff.get('active_milestone', '')}`",
        f"- block_reason: `{handoff.get('block_reason', '')}`",
        f"- next_recommended_workflow: `{handoff.get('next_recommended_workflow', '')}`",
        f"- next_ready_task_id: `{handoff.get('next_ready_task_id', '')}`",
        f"- next_ready_task_template: `{handoff.get('next_ready_task_template', '')}`",
        f"- program_stop_reason: `{handoff.get('program_stop_reason', '')}`",
        f"- updated_at: `{handoff.get('updated_at', '')}`",
        "",
        "## Completed Milestones",
        "",
    ]
    completed = list(handoff.get("completed_milestones", []))
    if completed:
        lines.extend(f"- `{item}`" for item in completed)
    else:
        lines.append("- `(none)`")
    lines.extend(
        [
            "",
            "## Top Decisions",
            "",
        ]
    )
    top_decisions = list(handoff.get("top_decisions", []))
    if top_decisions:
        lines.extend(f"- `{item}`" for item in top_decisions)
    else:
        lines.append("- `(none)`")
    lines.extend(
        [
            "",
            "## Best-known Snapshot",
            "",
            f"- best_val_l3_macro_f1: `{best_known.get('best_val_l3_macro_f1', '')}`",
            f"- best_val_multilabel_micro_f1: `{best_known.get('best_val_multilabel_micro_f1', '')}`",
            f"- best_test_multilabel_micro_f1: `{best_known.get('best_test_multilabel_micro_f1', '')}`",
            f"- best_gate_health_status: `{best_known.get('best_gate_health_status', '')}`",
            f"- source_experiment_id: `{best_known.get('source_experiment_id', '')}`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _workflow_conflicts_with_decisions(template_name: str, decisions: list[dict[str, Any]]) -> str:
    chosen = {str(item.get("topic", "")): str(item.get("chosen_option", "")) for item in decisions}
    blocked = {str(block) for item in decisions for block in item.get("blocks_workflows", []) if str(block).strip()}
    if "all" in template_name and chosen.get("restore_all_modalities") == "do_not_restore_all":
        return "decision_memory_blocks_restore_all"
    if template_name in blocked:
        return "decision_memory_blocks_workflow"
    if "gate_entropy" in template_name and chosen.get("multilabel_mainline_candidate") == "gate_load_balance":
        return "decision_memory_prefers_gate_load_balance"
    return ""


def _workflow_is_experiment_bearing(template_name: str) -> bool:
    template = WORKFLOW_TEMPLATES.get(template_name, {})
    experiment_stages = {
        "real_case_staging",
        "higher_budget_staging",
        "second_seed_higher_budget",
        "extended_real_case_staging",
        "selector_feasibility_smoke",
    }
    return any(stage in experiment_stages for stage in list(template.get("stages", [])))


def _materialize_placeholder(candidate: dict[str, Any]) -> str:
    task_path = Path(candidate["task_path"])
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(candidate["markdown"], encoding="utf-8")
    record_path = create_task(str(task_path), **candidate["create_kwargs"])
    record = get_task_record(Path(record_path).stem)
    record.update(candidate["record_overrides"])
    record["updated_at"] = _now_iso()
    save_task_record(record)
    return str(record["task_id"])


def _ensure_placeholder_tasks() -> dict[str, str]:
    mapping = {
        "selector_feasibility_smoke": "",
        "dual_output_implementation_plan": "",
        "inference_hold_closeout": "",
    }
    existing_by_template = {
        str(record.get("template_name", "")): record
        for record in list_task_records()
        if str(record.get("template_name", "")).strip()
    }
    for template_name in tuple(mapping.keys()):
        record = existing_by_template.get(template_name)
        if record:
            mapping[template_name] = str(record.get("task_id", ""))
            continue
        candidate = build_multilabel_phase2_placeholder(template_name, source_evidence_ids=["multilabel_inference_protocol_decision_ready"])
        task_id = _materialize_placeholder(candidate)
        mapping[template_name] = task_id
    return mapping


def _ensure_phase3_placeholder_tasks() -> dict[str, str]:
    mapping = {
        "dual_output_runtime_patch": "",
        "dual_output_report_closeout": "",
        "dual_output_hold_closeout": "",
    }
    existing_by_template = {
        str(record.get("template_name", "")): record
        for record in list_task_records()
        if str(record.get("template_name", "")).strip()
    }
    for template_name in tuple(mapping.keys()):
        record = existing_by_template.get(template_name)
        if record:
            mapping[template_name] = str(record.get("task_id", ""))
            continue
        candidate = build_multilabel_phase3_placeholder(template_name, source_evidence_ids=["dual_output_implementation_plan_ready"])
        task_id = _materialize_placeholder(candidate)
        mapping[template_name] = task_id
    return mapping


def _promote_placeholder_from_followup(decision_payload: dict[str, Any]) -> str:
    placeholders = _ensure_placeholder_tasks()
    next_action_hint = str(decision_payload.get("next_action_hint", "")).strip()
    requires_selector = bool(decision_payload.get("requires_selector_experiment", False))
    ready_for_implementation = bool(decision_payload.get("ready_for_implementation", False))
    if requires_selector:
        selected_template = "selector_feasibility_smoke"
    elif not requires_selector and ready_for_implementation and next_action_hint == "dual_output_implementation_plan":
        selected_template = "dual_output_implementation_plan"
    else:
        selected_template = "inference_hold_closeout"
    for template_name, task_id in placeholders.items():
        record = get_task_record(task_id)
        record["autopilot_enabled"] = False
        selected_status = "ready"
        if selected_template == "dual_output_implementation_plan":
            selected_status = "proposed"
        record["status"] = selected_status if template_name == selected_template else "proposed"
        record["updated_at"] = _now_iso()
        save_task_record(record)
    return placeholders[selected_template]


def _selected_phase2_placeholder() -> dict[str, Any] | None:
    for record in list_task_records():
        if str(record.get("template_name", "")) not in {
            "selector_feasibility_smoke",
            "dual_output_implementation_plan",
            "inference_hold_closeout",
        }:
            continue
        if str(record.get("status", "")) == "ready":
            return record
    return None


def _selected_phase3_placeholder() -> dict[str, Any] | None:
    priority = {
        "dual_output_report_closeout": 0,
        "dual_output_hold_closeout": 1,
        "dual_output_runtime_patch": 2,
    }
    ready_records = [
        record
        for record in list_task_records()
        if str(record.get("template_name", "")) in priority
        and str(record.get("status", "")) == "ready"
    ]
    if ready_records:
        ready_records.sort(
            key=lambda record: (
                priority.get(str(record.get("template_name", "")), 99),
                str(record.get("updated_at", "")),
                str(record.get("task_id", "")),
            )
        )
        return ready_records[0]
    return None


def _promote_placeholder_from_dual_output(decision_payload: dict[str, Any]) -> str:
    placeholders = _ensure_phase3_placeholder_tasks()
    requires_runtime_api_change = bool(decision_payload.get("requires_runtime_api_change", False))
    requires_model_output_change = bool(decision_payload.get("requires_model_output_change", False))
    next_action_hint = str(decision_payload.get("next_action_hint", "")).strip()
    if requires_runtime_api_change or requires_model_output_change or next_action_hint == "dual_output_runtime_patch":
        selected_template = "dual_output_runtime_patch"
    elif next_action_hint == "dual_output_report_closeout":
        selected_template = "dual_output_report_closeout"
    else:
        selected_template = "dual_output_hold_closeout"
    for template_name, task_id in placeholders.items():
        record = get_task_record(task_id)
        record["autopilot_enabled"] = False
        current_status = str(record.get("status", ""))
        if current_status == "completed":
            record["status"] = "completed"
        else:
            record["status"] = "ready" if template_name == selected_template else "proposed"
        record["updated_at"] = _now_iso()
        save_task_record(record)
    return placeholders[selected_template]


def _promote_placeholder_after_runtime_patch(decision_payload: dict[str, Any]) -> str:
    placeholders = _ensure_phase3_placeholder_tasks()
    next_action_hint = str(decision_payload.get("next_action_hint", "")).strip()
    if next_action_hint == "dual_output_report_closeout":
        selected_template = "dual_output_report_closeout"
    else:
        selected_template = "dual_output_hold_closeout"
    for template_name, task_id in placeholders.items():
        record = get_task_record(task_id)
        record["autopilot_enabled"] = False
        current_status = str(record.get("status", ""))
        if current_status == "completed":
            record["status"] = "completed"
        else:
            record["status"] = "ready" if template_name == selected_template else "proposed"
        record["updated_at"] = _now_iso()
        save_task_record(record)
    return placeholders[selected_template]


def _sync_decision_payloads_from_tasks() -> list[dict[str, Any]]:
    decisions = ensure_decision_memory()
    task_records = list_task_records()
    template_order = {
        "inference_protocol_decision": 0,
        "promotion_followup_decision": 1,
        "dual_output_plan_decision": 2,
        "dual_output_runtime_patch": 3,
    }
    task_records.sort(
        key=lambda item: (
            template_order.get(str(item.get("template_name", "")), 99),
            str(item.get("updated_at", "")),
            str(item.get("task_id", "")),
        )
    )
    completed_templates = {
        str(item.get("template_name", ""))
        for item in task_records
        if str(item.get("status", "")) == "completed"
    }
    runtime_patch_completed = "dual_output_runtime_patch" in completed_templates
    for task_record in task_records:
        if str(task_record.get("status", "")) != "completed":
            continue
        payload = task_record.get("decision_payload", {})
        if not isinstance(payload, dict) or not str(payload.get("topic", "")).strip():
            continue
        task_id = str(task_record.get("task_id", ""))
        topic = str(payload.get("topic", "")).strip()
        template_name = str(task_record.get("template_name", ""))
        if template_name == "inference_protocol_decision":
            entry = {
                "decision_id": f"{task_id}-decision",
                "topic": topic,
                "topic_kind": "inference_protocol",
                "chosen_option": str(payload.get("chosen_protocol", "")),
                "rejected_options": list(payload.get("rejected_protocols", [])),
                "evidence_ids": [task_id],
                "confidence": 0.8,
                "supersedes": [],
                "decision_status": "active",
                "next_action_hint": str(payload.get("next_action_hint", "")) or "promotion_candidate_followup",
                "blocks_workflows": [],
            }
            decisions = _upsert_decision(entry)
        elif template_name == "promotion_followup_decision":
            entry = {
                "decision_id": f"{task_id}-decision",
                "topic": "promotion_candidate_followup",
                "topic_kind": "promotion_policy",
                "chosen_option": str(payload.get("chosen_protocol", "")),
                "rejected_options": list(payload.get("rejected_protocols", [])),
                "evidence_ids": [task_id],
                "confidence": 0.8,
                "supersedes": [],
                "decision_status": "active",
                "next_action_hint": str(payload.get("next_action_hint", "")) or "hold_no_experiment",
                "blocks_workflows": [],
            }
            decisions = _upsert_decision(entry)
            _promote_placeholder_from_followup(payload)
        elif template_name == "dual_output_plan_decision":
            if not runtime_patch_completed:
                entry = {
                    "decision_id": f"{task_id}-decision",
                    "topic": "dual_output_implementation_plan",
                    "topic_kind": "runtime_scope",
                    "chosen_option": str(payload.get("chosen_protocol", "")),
                    "rejected_options": list(payload.get("rejected_protocols", [])),
                    "evidence_ids": [task_id],
                    "confidence": 0.8,
                    "supersedes": [],
                    "decision_status": "active",
                    "next_action_hint": str(payload.get("next_action_hint", "")) or "dual_output_runtime_patch",
                    "blocks_workflows": [],
                }
                decisions = _upsert_decision(entry)
                _promote_placeholder_from_dual_output(payload)
        elif template_name == "dual_output_runtime_patch":
            entry = {
                "decision_id": f"{task_id}-decision",
                "topic": "dual_output_implementation_plan",
                "topic_kind": "runtime_scope",
                "chosen_option": str(payload.get("chosen_protocol", "")),
                "rejected_options": list(payload.get("rejected_protocols", [])),
                "evidence_ids": [task_id],
                "confidence": 0.9,
                "supersedes": [],
                "decision_status": "active",
                "next_action_hint": str(payload.get("next_action_hint", "")) or "dual_output_report_closeout",
                "blocks_workflows": [],
            }
            decisions = _upsert_decision(entry)
            _promote_placeholder_after_runtime_patch(payload)
    return decisions


def _load_experiment_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(EXPERIMENT_REGISTRY_DIR.glob("*.json")):
        records.append(validate_experiment_record(load_json(path)).data)
    return records


def _best_known_micro_f1(records: list[dict[str, Any]]) -> float | None:
    values = [
        float(item["best_val_multilabel_micro_f1"])
        for item in records
        if item.get("best_val_multilabel_micro_f1") is not None
        and "gate_load_balance" in str(item.get("variant", ""))
    ]
    return max(values) if values else None


def _latest_gate_load_balance_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [item for item in records if "gate_load_balance" in str(item.get("variant", ""))]
    if not candidates:
        return None
    candidates.sort(key=lambda item: str(item.get("last_verified_at", "")) or str(item.get("experiment_id", "")))
    return candidates[-1]


def sync_best_known_metrics() -> dict[str, Any]:
    records = _load_experiment_records()
    current = default_best_known_metrics()
    for item in records:
        if str(item.get("closeout_status", "")) != "passed":
            continue
        if "gate_load_balance" not in str(item.get("variant", "")):
            continue
        current_best = current.get("best_val_multilabel_micro_f1")
        candidate = item.get("best_val_multilabel_micro_f1")
        if candidate is None:
            continue
        if current_best is None or float(candidate) > float(current_best):
            current["best_val_l3_macro_f1"] = item.get("best_val_l3_macro_f1")
            current["best_val_multilabel_micro_f1"] = candidate
            metrics_test_path = str(item.get("metrics_test_path", "") or "")
            current["best_test_multilabel_micro_f1"] = item.get("best_val_multilabel_micro_f1")
            current["best_gate_health_status"] = str(item.get("gate_health", {}).get("status", ""))
            current["best_mean_gates"] = dict(item.get("mean_gates", {}))
            current["source_experiment_id"] = str(item.get("experiment_id", ""))
            current["last_updated_at"] = _now_iso()
    return _write_best_known_metrics(current)


def sync_budget_state(policy: dict[str, Any] | None = None, *, force_reset: bool = False) -> dict[str, Any]:
    policy = policy or get_runtime_policy()
    state = _load_budget_state()
    today = datetime.now().astimezone().date().isoformat()
    experiment_tasks_today = [
        item
        for item in list_task_records()
        if str(item.get("workflow_kind", "")) == "experiment_run"
        and str(item.get("updated_at", "")).startswith(today)
        and str(item.get("status", "")) in ("running", "evaluating", "completed")
    ]
    reset_applied = force_reset or str(state.get("date", "")) != today
    if reset_applied:
        state = default_program_budget_state()
        state["date"] = today
        state["last_reset_at"] = _now_iso()
    state["date"] = today
    state["experiments_run_today"] = len(experiment_tasks_today)
    state["gpu_budget_minutes_used"] = min(
        int(policy.get("program_gpu_budget_minutes_per_day", 360)),
        len(experiment_tasks_today) * int(policy.get("experiment_max_wall_clock_minutes", 20)),
    )
    exhausted = state["experiments_run_today"] > int(policy.get("program_max_experiments_per_day", 3))
    state["budget_window_status"] = "exhausted" if exhausted else "open"
    saved = _write_budget_state(state)
    return {
        "date": saved["date"],
        "experiments_run_today": saved["experiments_run_today"],
        "gpu_budget_minutes_used": saved["gpu_budget_minutes_used"],
        "last_reset_at": saved["last_reset_at"],
        "budget_window_status": saved["budget_window_status"],
        "budget_reset": reset_applied,
    }


def evaluate_budget_guard(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or get_runtime_policy()
    budget_state = sync_budget_state(policy)
    exhausted = budget_state["budget_window_status"] == "exhausted"
    return {
        "budget_exhausted": exhausted,
        "budget_reason_code": "program_experiments_per_day_exhausted" if exhausted else "",
        "budget_summary": (
            f"experiment count today {budget_state['experiments_run_today']} exceeded limit"
            if exhausted
            else ""
        ),
        "recommended_action": "pause program until budget window resets" if exhausted else "",
        "budget_state": budget_state,
    }


def evaluate_program_regression() -> dict[str, Any]:
    records = _load_experiment_records()
    latest = _latest_gate_load_balance_record(records)
    if not latest:
        return {
            "regression_detected": False,
            "regression_reason_code": "",
            "regression_summary": "",
            "recommended_action": "",
        }
    best_known = sync_best_known_metrics()
    return evaluate_regression(
        gate_health=latest.get("gate_health", {}),
        mean_gates=latest.get("mean_gates", {}),
        closeout_status=str(latest.get("closeout_status", "")),
        required_artifacts_ok=bool(latest.get("summary_path")) and bool(latest.get("metrics_val_path")) and bool(latest.get("metrics_test_path")),
        current_multilabel_micro_f1=(
            float(latest["best_val_multilabel_micro_f1"]) if latest.get("best_val_multilabel_micro_f1") is not None else None
        ),
        best_known_multilabel_micro_f1=(
            float(best_known["best_val_multilabel_micro_f1"]) if best_known.get("best_val_multilabel_micro_f1") is not None else None
        ),
    )


def _workflow_stage_completed(workflow: dict[str, Any], stage: str) -> bool:
    return stage in list(workflow.get("completed_stages", []))


def _decision_topic_resolved(decisions: list[dict[str, Any]], topic: str) -> bool:
    for item in decisions:
        if str(item.get("topic", "")) != topic:
            continue
        if str(item.get("decision_status", "")) != "active":
            continue
        if str(item.get("next_action_hint", "")) in ("", "none"):
            return True
    return False


def _active_decision(decisions: list[dict[str, Any]], topic: str) -> dict[str, Any] | None:
    for item in decisions:
        if str(item.get("topic", "")) != topic:
            continue
        if str(item.get("decision_status", "")) != "active":
            continue
        return item
    return None


def _milestone_statuses(workflow: dict[str, Any] | None, decisions: list[dict[str, Any]]) -> dict[str, str]:
    workflow = workflow or {}
    template_name = str(workflow.get("template_name", ""))
    downstream_templates = {
        "multilabel_inference_protocol_decision",
        "promotion_candidate_followup",
        "dual_output_implementation_plan",
    }
    validation_complete = (
        template_name == "gate_load_balance_promotion" and _workflow_stage_completed(workflow, "second_seed_closeout")
    ) or template_name in downstream_templates
    promotion_complete = (
        template_name == "gate_load_balance_promotion" and _workflow_stage_completed(workflow, "promotion_candidate_decision")
    ) or template_name in downstream_templates
    inference_complete = template_name == "multilabel_inference_protocol_decision" and str(workflow.get("status", "")) == "completed"
    followup_complete = template_name == "promotion_candidate_followup" and str(workflow.get("status", "")) == "completed"
    followup_decision = _active_decision(decisions, "promotion_candidate_followup")
    dual_output_requested = str((followup_decision or {}).get("next_action_hint", "")) == "dual_output_implementation_plan"
    dual_output_complete = (
        template_name == "dual_output_implementation_plan" and str(workflow.get("status", "")) == "completed"
    ) or (_active_decision(decisions, "dual_output_implementation_plan") is not None)
    statuses = {
        "gate_load_balance_validation_complete": "completed" if validation_complete else "pending",
        "gate_load_balance_promotion_candidate": "completed" if promotion_complete else ("active" if validation_complete else "pending"),
        "multilabel_inference_protocol_decision_ready": (
            "completed"
            if inference_complete or followup_complete or dual_output_complete or _decision_topic_resolved(decisions, "multilabel_inference_selector")
            else ("active" if promotion_complete else "pending")
        ),
        "promotion_candidate_followup_pending": (
            "completed"
            if followup_complete or dual_output_complete or dual_output_requested
            else (
                "active"
                if promotion_complete and (inference_complete or _decision_topic_resolved(decisions, "multilabel_inference_selector"))
                else "pending"
            )
        ),
        "dual_output_implementation_plan_ready": (
            "completed"
            if dual_output_complete
            else ("active" if dual_output_requested else "pending")
        ),
    }
    return statuses


def recompute_program_state() -> dict[str, Any]:
    decisions = _sync_decision_payloads_from_tasks()
    _ensure_placeholder_tasks()
    _ensure_phase3_placeholder_tasks()
    workflow = active_workflow_instance()
    policy = get_runtime_policy()
    budget = evaluate_budget_guard(policy)
    regression = evaluate_program_regression()
    status_map = _milestone_statuses(workflow, decisions)
    selected_phase2 = _selected_phase2_placeholder()
    milestones: list[dict[str, Any]] = []
    source_evidence = list((workflow or {}).get("completed_stages", []))
    for blueprint in _milestone_blueprints():
        milestone = {
            **blueprint,
            "status": status_map.get(blueprint["milestone_id"], "pending"),
            "source_evidence_ids": source_evidence,
            "last_evaluated_at": _now_iso(),
            "block_reason": "",
        }
        milestones.append(milestone)

    program = load_program_state()
    program.update(default_program_state())
    program["primary_goal"] = PRIMARY_GOAL
    program["active_lane"] = "gate_load_balance"
    program["active_workflow_id"] = str((workflow or {}).get("workflow_id", ""))
    program["completed_milestones"] = [item["milestone_id"] for item in milestones if item["status"] == "completed"]
    active_milestone = next((item for item in milestones if item["status"] == "active"), None)
    program["current_milestone"] = str(active_milestone["milestone_id"]) if active_milestone else ""
    program["active_milestone"] = str(active_milestone["milestone_id"]) if active_milestone else ""
    program["blocked_milestones"] = [item["milestone_id"] for item in milestones if item["status"] == "blocked"]
    program["decision_memory_summary"] = [
        f"{item.get('topic','')}={item.get('chosen_option','')}"
        for item in decisions
    ]
    program["next_candidate_workflows"] = []
    program["next_workflow_template"] = ""
    program["next_recommended_workflow"] = ""
    program["program_block_reason"] = ""
    program["resume_after_budget_reset"] = False

    workflow_status = str((workflow or {}).get("status", ""))
    candidate_active_template = str((workflow or {}).get("template_name", "")) if workflow_status not in ("completed", "blocked", "paused") else ""
    candidate_next_template = ""
    if active_milestone:
        candidate_next_template = str(active_milestone.get("linked_workflow_template", ""))
    budget_blocks_program = bool(budget["budget_exhausted"]) and bool(policy.get("program_pause_on_budget_exhausted", True))
    selected_phase2 = _selected_phase2_placeholder()
    selected_phase3 = _selected_phase3_placeholder()
    if budget_blocks_program:
        if candidate_active_template and not _workflow_is_experiment_bearing(candidate_active_template):
            budget_blocks_program = False
        elif not candidate_active_template and candidate_next_template and not _workflow_is_experiment_bearing(candidate_next_template):
            budget_blocks_program = False

    if budget_blocks_program and selected_phase2 is None and selected_phase3 is None:
        program["status"] = "paused_for_human"
        program["program_block_reason"] = "budget_guard_triggered"
        program["resume_after_budget_reset"] = bool(active_milestone and active_milestone.get("auto_resume_allowed"))
    elif regression["regression_detected"]:
        program["status"] = "paused_for_human"
        program["program_block_reason"] = "regression_sentinel_triggered"
        if active_milestone:
            active_milestone["status"] = "blocked"
            active_milestone["block_reason"] = regression["regression_reason_code"]
            program["blocked_milestones"] = [active_milestone["milestone_id"]]
    elif workflow and str(workflow.get("status", "")) not in ("completed", "blocked", "paused"):
        program["status"] = "active"
    elif active_milestone:
        next_template = str(active_milestone.get("linked_workflow_template", ""))
        block = _workflow_conflicts_with_decisions(next_template, decisions) if next_template else ""
        if block:
            active_milestone["status"] = "blocked"
            active_milestone["block_reason"] = block
            program["status"] = "paused_for_human"
            program["program_block_reason"] = "program_blocked"
            program["blocked_milestones"] = [active_milestone["milestone_id"]]
        elif next_template and bool(workflow_template(next_template).get("auto_instantiation", False)):
            program["status"] = "active"
            program["next_workflow_template"] = next_template
            program["next_recommended_workflow"] = next_template
            program["next_candidate_workflows"] = [next_template]
        else:
            program["status"] = "paused_for_human"
            program["program_block_reason"] = "milestone_decision_required"
            if next_template:
                program["next_candidate_workflows"] = [next_template]
                program["next_workflow_template"] = next_template
                program["next_recommended_workflow"] = next_template
    elif selected_phase3 is not None:
        program["status"] = "paused_for_human"
        program["program_block_reason"] = "milestone_decision_required"
        program["next_recommended_workflow"] = str(selected_phase3.get("template_name", ""))
        program["next_candidate_workflows"] = [str(selected_phase3.get("task_id", ""))]
    elif selected_phase2 is not None:
        program["status"] = "paused_for_human"
        program["program_block_reason"] = "milestone_decision_required"
        program["next_recommended_workflow"] = str(selected_phase2.get("template_name", ""))
        program["next_candidate_workflows"] = [str(selected_phase2.get("task_id", ""))]
    else:
        program["status"] = "completed"

    program["last_program_summary"] = f"{program['status']}:{program['active_milestone'] or program['current_milestone']}"
    _write_milestones_state({"program_id": program["program_id"], "milestones": milestones})
    save_program_state(program)
    handoff = default_program_handoff()
    next_ready = selected_phase3 or (
        selected_phase2 if str((selected_phase2 or {}).get("template_name", "")) != "dual_output_implementation_plan" else None
    )
    handoff.update(
        {
            "program_id": program["program_id"],
            "primary_goal": program["primary_goal"],
            "active_lane": program["active_lane"],
            "active_milestone": program["active_milestone"],
            "completed_milestones": list(program["completed_milestones"]),
            "block_reason": program["program_block_reason"],
            "next_recommended_workflow": program["next_recommended_workflow"] or program["next_workflow_template"],
            "next_ready_task_id": str((next_ready or {}).get("task_id", "")),
            "next_ready_task_template": str((next_ready or {}).get("template_name", "")),
            "program_stop_reason": str(program["program_block_reason"] or program["status"]),
            "top_decisions": list(program["decision_memory_summary"][:5]),
            "best_known_metrics_snapshot": sync_best_known_metrics(),
            "updated_at": _now_iso(),
        }
    )
    _write_program_handoff(handoff)
    report_path = _write_program_summary_report(handoff)
    return {
        "program": validate_program_state(program).data,
        "milestones": milestones,
        "budget_guard": budget,
        "regression_sentinel": regression,
        "decisions": decisions,
        "best_known_metrics": sync_best_known_metrics(),
        "program_handoff": handoff,
        "program_summary_report": str(report_path),
    }


def ensure_program_progress() -> dict[str, Any]:
    snapshot = recompute_program_state()
    program = snapshot["program"]
    budget_reset = bool(snapshot["budget_guard"].get("budget_state", {}).get("budget_reset", False))
    workflow = active_workflow_instance()
    if workflow and str(workflow.get("status", "")) not in ("completed", "blocked", "paused"):
        return {
            "created_workflow": False,
            "workflow_id": str(workflow.get("workflow_id", "")),
            "program_status": str(program.get("status", "")),
            "budget_reset": budget_reset,
        }
    next_template = str(program.get("next_workflow_template", "")).strip()
    if not next_template:
        return {
            "created_workflow": False,
            "workflow_id": "",
            "program_status": str(program.get("status", "")),
            "budget_reset": budget_reset,
        }
    if not bool(workflow_template(next_template).get("auto_instantiation", False)):
        return {
            "created_workflow": False,
            "workflow_id": "",
            "program_status": str(program.get("status", "")),
            "budget_reset": budget_reset,
        }
    existing = active_workflow_instance()
    if existing and str(existing.get("template_name", "")) == next_template:
        return {
            "created_workflow": False,
            "workflow_id": str(existing.get("workflow_id", "")),
            "program_status": str(program.get("status", "")),
            "budget_reset": budget_reset,
        }
    if _workflow_conflicts_with_decisions(next_template, snapshot["decisions"]):
        return {
            "created_workflow": False,
            "workflow_id": "",
            "program_status": "paused_for_human",
            "budget_reset": budget_reset,
        }
    created = create_workflow_instance(next_template, lane="gate_load_balance")
    append_event(
        "workflow_instantiated",
        state_status="context_ready",
        reason_code="workflow_stage_advanced",
        details={
            "workflow_id": str(created.get("workflow_id", "")),
            "template_name": next_template,
            "milestone": str(program.get("active_milestone", "")),
        },
    )
    snapshot = recompute_program_state()
    return {
        "created_workflow": True,
        "workflow_id": str(created.get("workflow_id", "")),
        "program_status": str(snapshot["program"].get("status", "")),
        "budget_reset": budget_reset,
    }


def reset_budget_window() -> dict[str, Any]:
    state = sync_budget_state(force_reset=True)
    snapshot = recompute_program_state()
    return {
        "budget_state": state,
        "program": snapshot["program"],
    }


def show_milestones() -> dict[str, Any]:
    snapshot = recompute_program_state()
    return {
        "program_id": snapshot["program"]["program_id"],
        "milestones": snapshot["milestones"],
    }


def show_program_plan() -> dict[str, Any]:
    snapshot = recompute_program_state()
    return {
        "program": snapshot["program"],
        "milestones": snapshot["milestones"],
        "workflow": show_workflow_status().get("workflow", {}),
        "budget_guard": snapshot["budget_guard"],
        "regression_sentinel": snapshot["regression_sentinel"],
        "best_known_metrics": snapshot["best_known_metrics"],
        "program_handoff": snapshot["program_handoff"],
    }


def show_program_status() -> dict[str, Any]:
    snapshot = recompute_program_state()
    program = dict(snapshot["program"])
    program["active_milestone"] = program.get("active_milestone", "")
    program["completed_milestones"] = list(program.get("completed_milestones", []))
    program["blocked_milestones"] = list(program.get("blocked_milestones", []))
    program["next_workflow_template"] = str(program.get("next_workflow_template", ""))
    program["next_recommended_workflow"] = str(program.get("next_recommended_workflow", ""))
    program["decision_memory_summary"] = list(program.get("decision_memory_summary", []))
    return program


def show_budget_state() -> dict[str, Any]:
    sync_budget_state()
    return _load_budget_state()


def show_best_known() -> dict[str, Any]:
    return sync_best_known_metrics()


def show_program_handoff() -> dict[str, Any]:
    snapshot = recompute_program_state()
    return snapshot["program_handoff"]
