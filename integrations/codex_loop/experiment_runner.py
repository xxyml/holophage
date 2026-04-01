from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.artifacts import build_experiment_registry_draft, text_excerpt
from integrations.codex_loop.constants import EXPERIMENT_TRANSCRIPT_NAME, REPO_ROOT
from integrations.codex_loop.executor_runner import CommandResult, run_skill


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _command_prefix(command_text: str) -> str:
    stripped = command_text.strip()
    return stripped.split()[0].lower() if stripped else ""


def validate_experiment_command_against_policy(command_text: str, policy: dict[str, Any]) -> tuple[bool, str]:
    normalized = command_text.strip()
    lowered = normalized.lower()
    prefix = _command_prefix(normalized)
    forbidden_prefixes = {str(item).lower() for item in policy.get("experiment_forbidden_command_prefixes", [])}
    forbidden_substrings = [str(item).lower() for item in policy.get("experiment_forbidden_command_substrings", [])]
    allowed_prefixes = {str(item).lower() for item in policy.get("experiment_allowed_command_prefixes", [])}
    if prefix in forbidden_prefixes:
        return False, "experiment_forbidden_command_prefix"
    if any(token in lowered for token in forbidden_substrings):
        return False, "experiment_forbidden_command_substring"
    if prefix not in allowed_prefixes:
        return False, "experiment_forbidden_command_prefix"
    return True, ""


def _append_transcript_item(path: Path, *, step: str, command: str, exit_code: int, duration_ms: int, artifacts_detected: list[str], status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "step": step,
        "command": command,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "artifacts_detected": list(artifacts_detected),
        "status": status,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run_command(command_text: str, *, timeout_minutes: int) -> CommandResult:
    proc = subprocess.run(
        ["pwsh", "-Command", command_text],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=max(60, timeout_minutes * 60),
    )
    return CommandResult(
        skill="experiment-command",
        command=command_text,
        args={},
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _run_check_command(command_text: str) -> CommandResult:
    proc = subprocess.run(
        ["pwsh", "-Command", command_text],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return CommandResult(
        skill="required-check",
        command=command_text,
        args={},
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def execute_experiment(decision: dict[str, Any], *, policy: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    action_args = dict(decision.get("action", {}).get("args", {}))
    command_text = str(action_args.get("command", "")).strip()
    run_dir_arg = str(action_args.get("run_dir", "")).strip()
    config_path = str(action_args.get("config_path", "")).strip()
    experiment_dir = (REPO_ROOT / run_dir_arg).resolve() if run_dir_arg else run_dir
    transcript_path = run_dir / EXPERIMENT_TRANSCRIPT_NAME
    if transcript_path.exists():
        transcript_path.unlink()

    required_checks = [str(item).strip() for item in decision.get("required_checks", []) if str(item).strip()]
    required_artifacts = [
        str(item).strip()
        for item in (decision.get("experiment_required_artifacts", []) or policy.get("experiment_required_artifacts", []))
        if str(item).strip()
    ]
    if bool(policy.get("experiment_require_summary_json", True)) and "summary.json" not in required_artifacts:
        required_artifacts.append("summary.json")
    if bool(policy.get("experiment_require_metrics", False)):
        for rel in ("evaluation/metrics_val.json", "evaluation/metrics_test.json"):
            if rel not in required_artifacts:
                required_artifacts.append(rel)

    detected_conditions: list[str] = []
    fail_fast = False
    failed_step = ""
    step_count = 0

    preflight_started = time.perf_counter()
    preflight_result = run_skill("active-truth-calibration", {"format": "json"})
    preflight_duration_ms = int((time.perf_counter() - preflight_started) * 1000)
    preflight_status = "pass" if preflight_result.exit_code == 0 else "fail_fast"
    _append_transcript_item(
        transcript_path,
        step="preflight",
        command=preflight_result.command,
        exit_code=preflight_result.exit_code,
        duration_ms=preflight_duration_ms,
        artifacts_detected=[],
        status=preflight_status,
    )
    step_count += 1
    if preflight_result.exit_code != 0:
        fail_fast = True
        failed_step = "preflight"
        detected_conditions.append("active_truth_conflict")

    allowed, reason_code = validate_experiment_command_against_policy(command_text, policy)
    if not command_text:
        fail_fast = True
        failed_step = failed_step or "experiment_command"
        detected_conditions.append("experiment_missing_command")
    elif not allowed:
        fail_fast = True
        failed_step = failed_step or "experiment_command"
        detected_conditions.append(reason_code)

    command_started = time.perf_counter()
    action_result = _run_command(
        command_text,
        timeout_minutes=int(policy.get("experiment_max_wall_clock_minutes", 20)),
    ) if not fail_fast else CommandResult(
        skill="experiment-command",
        command=command_text or "<missing>",
        args={},
        exit_code=1,
        stdout="",
        stderr="experiment preconditions failed",
    )
    command_duration_ms = int((time.perf_counter() - command_started) * 1000)
    _append_transcript_item(
        transcript_path,
        step="experiment_command",
        command=action_result.command,
        exit_code=action_result.exit_code,
        duration_ms=command_duration_ms,
        artifacts_detected=[],
        status="pass" if action_result.exit_code == 0 else "fail",
    )
    step_count += 1
    if action_result.exit_code != 0 and not failed_step:
        failed_step = "experiment_command"

    existing_artifacts = [rel for rel in required_artifacts if (experiment_dir / rel).exists()]
    missing_artifacts = [rel for rel in required_artifacts if not (experiment_dir / rel).exists()]
    if missing_artifacts and bool(policy.get("experiment_pause_on_missing_artifacts", True)):
        detected_conditions.extend(f"missing_required_artifact:{item}" for item in missing_artifacts)
        fail_fast = True
        failed_step = failed_step or "artifact_scan"
    _append_transcript_item(
        transcript_path,
        step="artifact_scan",
        command=f"scan {experiment_dir}",
        exit_code=0 if not missing_artifacts else 1,
        duration_ms=0,
        artifacts_detected=existing_artifacts,
        status="pass" if not missing_artifacts else "fail",
    )
    step_count += 1

    checks_run: list[str] = []
    checks_passed: list[str] = []
    check_results: list[dict[str, Any]] = []
    for command in required_checks:
        check_started = time.perf_counter()
        result = _run_check_command(command)
        check_duration_ms = int((time.perf_counter() - check_started) * 1000)
        checks_run.append(command)
        if result.exit_code == 0:
            checks_passed.append(command)
        else:
            detected_conditions.append(f"failed_required_check:{command}")
            failed_step = failed_step or f"required_check:{command}"
        check_results.append(
            {
                "command": command,
                "exit_code": result.exit_code,
                "stdout_excerpt": text_excerpt(result.stdout),
                "stderr_excerpt": text_excerpt(result.stderr),
            }
        )
        _append_transcript_item(
            transcript_path,
            step=f"required_check:{command}",
            command=command,
            exit_code=result.exit_code,
            duration_ms=check_duration_ms,
            artifacts_detected=[],
            status="pass" if result.exit_code == 0 else "fail",
        )
        step_count += 1

    registry_preview: dict[str, Any] = {}
    if run_dir_arg and experiment_dir.exists():
        try:
            registry_preview = build_experiment_registry_draft(experiment_dir, task_id=decision["task_id"], config_path=config_path or None)
        except Exception:
            registry_preview = {}
    _append_transcript_item(
        transcript_path,
        step="registry_sync_preview",
        command=f"sync_experiment_from_run {experiment_dir}",
        exit_code=0 if registry_preview else 1,
        duration_ms=0,
        artifacts_detected=[str(registry_preview.get("experiment_id", ""))] if registry_preview else [],
        status="pass" if registry_preview else "fail",
    )
    step_count += 1

    closeout_status = "ready" if not missing_artifacts and action_result.exit_code == 0 else "failed"
    _append_transcript_item(
        transcript_path,
        step="closeout_validation",
        command="validate closeout readiness",
        exit_code=0 if closeout_status == "ready" else 1,
        duration_ms=0,
        artifacts_detected=existing_artifacts,
        status="pass" if closeout_status == "ready" else "fail",
    )
    step_count += 1
    if closeout_status != "ready" and not failed_step:
        failed_step = "closeout_validation"

    return {
        "schema_version": int(decision["schema_version"]),
        "run_id": decision["run_id"],
        "task_id": decision["task_id"],
        "linked_experiment_id": decision.get("linked_experiment_id", ""),
        "preflight": {
            "skill": preflight_result.skill,
            "exit_code": preflight_result.exit_code,
            "status": preflight_status,
            "stdout_excerpt": text_excerpt(preflight_result.stdout),
            "stderr_excerpt": text_excerpt(preflight_result.stderr),
            "stdout_json": {},
        },
        "action": {
            "kind": "experiment",
            "name": decision["action"]["name"],
            "command": action_result.command,
            "args": action_args,
            "exit_code": action_result.exit_code,
            "stdout_excerpt": text_excerpt(action_result.stdout),
            "stderr_excerpt": text_excerpt(action_result.stderr),
            "stdout_json": {},
        },
        "artifacts": {
            "run_dir": str(experiment_dir),
            "required_artifacts": required_artifacts,
            "existing_artifacts": existing_artifacts,
            "missing_artifacts": missing_artifacts,
            "check_results": check_results,
            "registry_preview": registry_preview,
            "closeout_status": closeout_status,
        },
        "machine_assessment": {
            "fail_fast": fail_fast,
            "completed_execution": action_result.exit_code == 0 and not missing_artifacts,
            "detected_conditions": detected_conditions,
        },
        "write_set": [_repo_relative(experiment_dir)] if run_dir_arg else [],
        "checks_run": checks_run,
        "checks_passed": checks_passed,
        "transcript_path": str(transcript_path),
        "step_count": step_count,
        "failed_step": failed_step,
        "progress_delta": {
            "summary": f"experiment exit_code={action_result.exit_code}; artifacts={len(existing_artifacts)}/{len(required_artifacts)}",
            "fingerprint": f"experiment|{action_result.exit_code}|{closeout_status}|{','.join(existing_artifacts)}",
        },
    }
