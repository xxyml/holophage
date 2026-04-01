from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import (
    ACTIVE_PATHS_PATH,
    ACTIVE_RUNTIME_CONTRACT_PATH,
    ACTIVE_VERSION_PATH,
    CURRENT_SPRINT_PATH,
    HANDOFF_DIR,
    REPORTS_DIR,
    TASKS_DIR,
)


def build_context_sources() -> dict[str, str]:
    return {
        "active_version": str(ACTIVE_VERSION_PATH),
        "active_paths": str(ACTIVE_PATHS_PATH),
        "active_runtime_contract": str(ACTIVE_RUNTIME_CONTRACT_PATH),
        "current_sprint": str(CURRENT_SPRINT_PATH),
        "tasks_dir": str(TASKS_DIR),
        "handoff_dir": str(HANDOFF_DIR),
        "reports_dir": str(REPORTS_DIR),
    }


def get_allowed_unattended_workflows(policy: dict[str, Any]) -> list[str]:
    values = policy.get("allowed_unattended_workflow_kinds", [])
    return [str(item) for item in values if isinstance(item, str)]


def is_progress_meaningful(execution: dict[str, Any], verdict: dict[str, Any], state: dict[str, Any]) -> bool:
    if verdict.get("objective_met"):
        return True
    progress = execution.get("progress_delta", {})
    fingerprint = str(progress.get("fingerprint", "")).strip()
    if fingerprint and fingerprint != str(state.get("last_progress_fingerprint", "")).strip():
        return True
    if execution.get("checks_passed"):
        return True
    if execution.get("write_set"):
        return True
    return False


def task_priority_key(task_record: dict[str, Any], current_sprint_text: str) -> tuple[int, int, str, str]:
    task_id = str(task_record.get("task_id", ""))
    in_sprint = 0 if task_id and task_id in current_sprint_text else 1
    priority = int(task_record.get("priority", 100))
    last_attempt = str(task_record.get("last_attempt_at", ""))
    return (priority, in_sprint, last_attempt or "", task_id)


def is_task_in_cooldown(task_record: dict[str, Any], *, now_iso: str) -> bool:
    cooldown_until = str(task_record.get("cooldown_until", "")).strip()
    return bool(cooldown_until and cooldown_until > now_iso)


def resolve_task_file(task_record: dict[str, Any]) -> Path:
    return Path(str(task_record.get("task_doc_path", "")))
