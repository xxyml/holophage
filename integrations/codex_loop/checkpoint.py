from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import (
    EXECUTION_RESULT_NAME,
    PLANNER_DECISION_NAME,
    PLANNER_PACKET_NAME,
    REVIEW_VERDICT_NAME,
    STAGE_CHECKPOINT_NAME,
)
from integrations.codex_loop.schemas import load_json, validate_stage_checkpoint, write_json


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def checkpoint_path(run_dir: Path) -> Path:
    return run_dir / STAGE_CHECKPOINT_NAME


def _artifact_flags(run_dir: Path) -> dict[str, bool]:
    return {
        "planner_input_packet": (run_dir / PLANNER_PACKET_NAME).exists(),
        "planner_decision": (run_dir / PLANNER_DECISION_NAME).exists(),
        "execution_result": (run_dir / EXECUTION_RESULT_NAME).exists(),
        "review_verdict": (run_dir / REVIEW_VERDICT_NAME).exists(),
    }


def write_stage_checkpoint(
    run_dir: Path,
    *,
    run_id: str,
    task_id: str,
    runner_id: str,
    stage: str,
    state_status: str,
    resume_hint: str,
) -> Path:
    payload = validate_stage_checkpoint(
        {
            "checkpoint_version": 1,
            "run_id": run_id,
            "task_id": task_id,
            "runner_id": runner_id,
            "stage": stage,
            "state_status": state_status,
            "updated_at": _now_iso(),
            "resume_hint": resume_hint,
            "artifacts_ready": _artifact_flags(run_dir),
        }
    ).data
    path = checkpoint_path(run_dir)
    write_json(path, payload)
    return path


def load_stage_checkpoint(run_dir: Path) -> dict[str, Any] | None:
    path = checkpoint_path(run_dir)
    if not path.exists():
        return None
    return validate_stage_checkpoint(load_json(path)).data
