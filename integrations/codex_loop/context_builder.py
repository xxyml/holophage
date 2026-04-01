from __future__ import annotations

import json
import re
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from integrations.codex_loop.constants import (
    ACTIVE_PATHS_PATH,
    ACTIVE_RUNTIME_CONTRACT_PATH,
    ACTIVE_VERSION_PATH,
    CURRENT_SPRINT_PATH,
    EXECUTION_RESULT_NAME,
    HANDOFF_DIR,
    LOOP_RUNS_DIR,
    PLANNER_PACKET_NAME,
    REVIEW_VERDICT_NAME,
    ROUND_SUMMARY_NAME,
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    SKILL_ROUTING_PATH,
    TASKS_DIR,
)
from integrations.codex_loop.project_profile import build_context_sources
from integrations.codex_loop.schemas import load_json

TASK_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+/tasks/[^)]+\.md)\)")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(_read_text(path))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected YAML mapping: {path}")
    return _json_safe(payload)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _latest_markdown(directory: Path) -> Path | None:
    candidates = [path for path in directory.glob("*.md") if path.name.lower() != "readme.md"]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _task_from_current_sprint(current_sprint_text: str) -> Path | None:
    matches = TASK_LINK_RE.findall(current_sprint_text)
    for raw in matches:
        path = Path(raw)
        if path.exists():
            return path
    return None


def _extract_current_focus(current_sprint_text: str) -> str:
    marker = "本轮只做一件事："
    if marker not in current_sprint_text:
        return ""
    _, _, tail = current_sprint_text.partition(marker)
    for line in tail.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            return stripped[2:].strip()
        if stripped.startswith("## "):
            break
    return ""


def _infer_phase(current_focus: str, handoff_text: str, task_payload: dict[str, Any] | None) -> str:
    corpus = f"{current_focus}\n{handoff_text}\n{task_payload or ''}".lower()
    if "multilabel" in corpus:
        return "multilabel_transition"
    if "governance" in corpus:
        return "governance_alignment"
    if "closeout" in corpus or "收口" in corpus:
        return "results_closeout"
    if "implement" in corpus or "实现" in corpus:
        return "implementation"
    return "general_execution"


def _load_latest_loop_context() -> dict[str, Any] | None:
    if not LOOP_RUNS_DIR.exists():
        return None
    candidates = [path for path in LOOP_RUNS_DIR.iterdir() if path.is_dir()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item.stat().st_mtime)
    payload: dict[str, Any] = {
        "run_id": latest.name,
        "path": str(latest),
    }
    for filename in (PLANNER_PACKET_NAME, EXECUTION_RESULT_NAME, REVIEW_VERDICT_NAME, ROUND_SUMMARY_NAME):
        file_path = latest / filename
        if not file_path.exists():
            continue
        if file_path.suffix == ".json":
            payload[filename] = json.loads(file_path.read_text(encoding="utf-8"))
        else:
            payload[filename] = file_path.read_text(encoding="utf-8")
    return payload


def _load_task_payload(task_file: Path | None) -> dict[str, Any] | None:
    if task_file and task_file.exists():
        return {
            "task_id": task_file.stem,
            "path": str(task_file),
            "content": _read_text(task_file),
        }
    return None


def build_context_packet(
    run_id: str,
    task_id: str | None = None,
    task_file: Path | None = None,
    handoff_file: Path | None = None,
    task_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_sprint_text = _read_text(CURRENT_SPRINT_PATH)
    resolved_task = task_file
    if resolved_task is None and task_id:
        candidate = TASKS_DIR / f"{task_id}.md"
        if candidate.exists():
            resolved_task = candidate
    if resolved_task is None:
        resolved_task = _task_from_current_sprint(current_sprint_text) or _latest_markdown(TASKS_DIR)
    resolved_handoff = handoff_file or _latest_markdown(HANDOFF_DIR)

    task_payload = _load_task_payload(resolved_task)
    handoff_payload = None
    handoff_text = ""
    if resolved_handoff and resolved_handoff.exists():
        handoff_text = _read_text(resolved_handoff)
        handoff_payload = {
            "path": str(resolved_handoff),
            "content": handoff_text,
        }

    active_version = _read_yaml(ACTIVE_VERSION_PATH)
    current_focus = _extract_current_focus(current_sprint_text)
    if task_record and isinstance(task_record.get("objective"), str) and task_record["objective"].strip():
        current_focus = task_record["objective"]
    phase_hint = _infer_phase(current_focus=current_focus, handoff_text=handoff_text, task_payload=task_payload)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "phase_hint": phase_hint,
        "current_focus": current_focus,
        "task_id": task_id or (task_payload.get("task_id") if task_payload else ""),
        "paths": {
            **build_context_sources(),
            "skill_registry": str(SKILL_REGISTRY_PATH),
            "skill_routing": str(SKILL_ROUTING_PATH),
        },
        "truth": {
            "active_version": active_version,
            "active_paths": _read_yaml(ACTIVE_PATHS_PATH),
            "active_runtime_contract_text": _read_text(ACTIVE_RUNTIME_CONTRACT_PATH),
            "current_sprint_text": current_sprint_text,
            "official_phrases": [
                "PFO v1.0.2",
                active_version.get("active_truth", {}).get("split_version", ""),
                active_version.get("active_truth", {}).get("sequence_embedding_key", ""),
                "L1 + L2 + L3 core",
                active_version.get("active_truth", {}).get("target_status_primary", ""),
            ],
        },
        "current_task": task_payload,
        "task_record": task_record or {},
        "latest_handoff": handoff_payload,
        "latest_loop_context": _load_latest_loop_context(),
        "skills": {
            "registry": json.loads(_read_text(SKILL_REGISTRY_PATH)),
            "routing_text": _read_text(SKILL_ROUTING_PATH),
        },
    }
