from __future__ import annotations

import difflib
import hashlib
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.artifacts import text_excerpt
from integrations.codex_loop.constants import (
    EXECUTION_RESULT_NAME,
    IMPLEMENTATION_TRANSCRIPT_NAME,
    IMPLEMENTATION_WORKSPACE_NAME,
    PLANNER_DECISION_NAME,
    REPO_ROOT,
)
from integrations.codex_loop.executor_runner import CommandResult, run_skill


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_allowed_paths(paths: list[str]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for item in paths:
        resolved = (REPO_ROOT / item).resolve()
        rel = _repo_relative(resolved)
        if resolved.exists() and resolved.is_file():
            snapshot[rel] = _hash_file(resolved)
        else:
            snapshot[rel] = ""
    return snapshot


def snapshot_allowed_path_texts(paths: list[str]) -> dict[str, list[str]]:
    snapshot: dict[str, list[str]] = {}
    for item in paths:
        resolved = (REPO_ROOT / item).resolve()
        rel = _repo_relative(resolved)
        if resolved.exists() and resolved.is_file():
            snapshot[rel] = resolved.read_text(encoding="utf-8").splitlines()
        else:
            snapshot[rel] = []
    return snapshot


def snapshot_repo_changes() -> set[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        return set()
    changed: set[str] = set()
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        path_text = line[3:].strip()
        if not path_text:
            continue
        changed.add(path_text.replace("\\", "/"))
    return changed


def build_implementation_prompt(decision: dict[str, Any], workspace_path: Path) -> str:
    allowed_write_paths = list(decision.get("allowed_write_paths", []))
    required_checks = list(decision.get("required_checks", []))
    return "\n".join(
        [
            "You are executing a constrained Holophage V2.2 implementation task.",
            f"Objective: {decision['objective']}",
            f"Planner decision: {workspace_path.parent / PLANNER_DECISION_NAME}",
            f"Implementation workspace: {workspace_path}",
            f"Required output: {workspace_path.parent / EXECUTION_RESULT_NAME}",
            "",
            "Hard rules:",
            "- Only modify files in allowed_write_paths.",
            "- Do not modify manifests, ontology, defaults, or active truth assets.",
            "- Complete exactly one small objective.",
            "- Run every required check.",
            "- Do not use destructive commands.",
            "",
            "allowed_write_paths:",
            *[f"- {item}" for item in allowed_write_paths],
            "",
            "required_checks:",
            *[f"- {item}" for item in required_checks],
            "",
            "After edits and checks, stop. The outer runner will collect write_set and check results.",
        ]
    )


def run_codex_implementation(prompt: str) -> CommandResult:
    codex_cmd = Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd"
    argv = [
        str(codex_cmd),
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--full-auto",
        "--skip-git-repo-check",
        "-",
    ]
    proc = subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=prompt,
    )
    return CommandResult(
        skill="codex-implementation",
        command=subprocess.list2cmdline(argv),
        args={},
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def run_check_command(command_text: str) -> CommandResult:
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


def diff_line_count(before_texts: dict[str, list[str]], after_texts: dict[str, list[str]], paths: list[str]) -> int:
    total = 0
    for path in paths:
        before_lines = before_texts.get(path, [])
        after_lines = after_texts.get(path, [])
        matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            total += max(i2 - i1, j2 - j1)
    return total


def _command_prefix(command_text: str) -> str:
    stripped = command_text.strip()
    if not stripped:
        return ""
    return stripped.split()[0].lower()


def validate_command_against_policy(command_text: str, policy: dict[str, Any], *, is_check: bool) -> tuple[bool, str]:
    normalized = command_text.strip()
    lowered = normalized.lower()
    forbidden_prefixes = {str(item).lower() for item in policy.get("implementation_forbidden_command_prefixes", [])}
    forbidden_substrings = [str(item).lower() for item in policy.get("implementation_forbidden_command_substrings", [])]
    prefix = _command_prefix(normalized)

    if prefix in forbidden_prefixes:
        return False, "implementation_forbidden_check_prefix" if is_check else "implementation_forbidden_command_prefix"
    if any(token in lowered for token in forbidden_substrings):
        return False, "implementation_forbidden_command_substring"
    if is_check:
        allowed_prefixes = {str(item).lower() for item in policy.get("implementation_allowed_command_prefixes", [])}
        if prefix not in allowed_prefixes:
            return False, "implementation_forbidden_check_prefix"
    return True, ""


def _append_transcript_item(path: Path, *, step: str, command: str, exit_code: int, duration_ms: int, changed_paths: list[str], status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "step": step,
        "command": command,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "changed_paths": list(changed_paths),
        "status": status,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def execute_implementation(
    decision: dict[str, Any],
    *,
    policy: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    allowed_write_paths = [str(item).replace("\\", "/") for item in decision.get("allowed_write_paths", []) if str(item).strip()]
    required_checks = [str(item).strip() for item in decision.get("required_checks", []) if str(item).strip()]
    workspace_path = run_dir / IMPLEMENTATION_WORKSPACE_NAME
    transcript_path = run_dir / IMPLEMENTATION_TRANSCRIPT_NAME
    if transcript_path.exists():
        transcript_path.unlink()
    step_count = 0
    failed_step = ""

    preflight_started = time.perf_counter()
    preflight_result = run_skill("active-truth-calibration", {"format": "json"})
    preflight_duration_ms = int((time.perf_counter() - preflight_started) * 1000)
    preflight_status = "pass" if preflight_result.exit_code == 0 else "fail_fast"
    detected_conditions: list[str] = []
    fail_fast = preflight_result.exit_code != 0
    _append_transcript_item(
        transcript_path,
        step="preflight",
        command=preflight_result.command,
        exit_code=preflight_result.exit_code,
        duration_ms=preflight_duration_ms,
        changed_paths=[],
        status=preflight_status,
    )
    step_count += 1
    if preflight_result.exit_code != 0 and not failed_step:
        failed_step = "preflight"

    if not allowed_write_paths:
        fail_fast = True
        detected_conditions.append("implementation_missing_allowed_write_paths")
    if not required_checks:
        fail_fast = True
        detected_conditions.append("implementation_missing_required_checks")

    invalid_checks = []
    for item in required_checks:
        ok, reason_code = validate_command_against_policy(item, policy, is_check=True)
        if not ok:
            invalid_checks.append({"command": item, "reason_code": reason_code})
    if invalid_checks:
        fail_fast = True
        detected_conditions.extend(sorted({item["reason_code"] for item in invalid_checks}))

    before_allowed = snapshot_allowed_paths(allowed_write_paths)
    before_allowed_texts = snapshot_allowed_path_texts(allowed_write_paths)
    before_repo_changes = snapshot_repo_changes()
    prompt = build_implementation_prompt(decision, workspace_path)
    action_started = time.perf_counter()
    action_preview = subprocess.list2cmdline(
        [
            str(Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd"),
            "exec",
            "--cd",
            str(REPO_ROOT),
            "--full-auto",
            "--skip-git-repo-check",
            "-",
        ]
    )
    action_allowed, action_reason_code = validate_command_against_policy(action_preview, policy, is_check=False)
    if not action_allowed:
        fail_fast = True
        detected_conditions.append(action_reason_code)
        if not failed_step:
            failed_step = "implementation_command"
    action_result = run_codex_implementation(prompt) if not fail_fast else CommandResult(
        skill="codex-implementation",
        command=action_preview,
        args={},
        exit_code=1,
        stdout="",
        stderr="implementation preconditions failed",
    )
    action_duration_ms = int((time.perf_counter() - action_started) * 1000)

    after_allowed = snapshot_allowed_paths(allowed_write_paths)
    after_allowed_texts = snapshot_allowed_path_texts(allowed_write_paths)
    after_repo_changes = snapshot_repo_changes()

    changed_allowed = sorted(path for path, digest in after_allowed.items() if digest != before_allowed.get(path, ""))
    repo_delta = sorted(after_repo_changes - before_repo_changes)
    out_of_scope = sorted(path for path in repo_delta if path not in set(allowed_write_paths))
    write_set = sorted(set(changed_allowed) | set(repo_delta))
    _append_transcript_item(
        transcript_path,
        step="implementation_command",
        command=action_result.command,
        exit_code=action_result.exit_code,
        duration_ms=action_duration_ms,
        changed_paths=write_set,
        status="pass" if action_result.exit_code == 0 else "fail",
    )
    step_count += 1
    if action_result.exit_code != 0 and not failed_step:
        failed_step = "implementation_command"

    checks_run: list[str] = []
    checks_passed: list[str] = []
    check_results: list[dict[str, Any]] = []
    checks_started = time.perf_counter()
    for command_text in required_checks:
        allowed, reason_code = validate_command_against_policy(command_text, policy, is_check=True)
        if not allowed:
            detected_conditions.append(reason_code)
            check_results.append(
                {
                    "command": command_text,
                    "exit_code": 1,
                    "stdout_excerpt": "",
                    "stderr_excerpt": reason_code,
                }
            )
            checks_run.append(command_text)
            _append_transcript_item(
                transcript_path,
                step=f"required_check:{command_text}",
                command=command_text,
                exit_code=1,
                duration_ms=0,
                changed_paths=[],
                status="blocked",
            )
            step_count += 1
            if not failed_step:
                failed_step = f"required_check:{command_text}"
            continue
        check_started = time.perf_counter()
        result = run_check_command(command_text)
        check_duration_ms = int((time.perf_counter() - check_started) * 1000)
        checks_run.append(command_text)
        if result.exit_code == 0:
            checks_passed.append(command_text)
        check_results.append(
            {
                "command": command_text,
                "exit_code": result.exit_code,
                "stdout_excerpt": text_excerpt(result.stdout),
                "stderr_excerpt": text_excerpt(result.stderr),
            }
        )
        _append_transcript_item(
            transcript_path,
            step=f"required_check:{command_text}",
            command=command_text,
            exit_code=result.exit_code,
            duration_ms=check_duration_ms,
            changed_paths=[],
            status="pass" if result.exit_code == 0 else "fail",
        )
        step_count += 1
        if result.exit_code != 0 and not failed_step:
            failed_step = f"required_check:{command_text}"
    checks_duration_ms = int((time.perf_counter() - checks_started) * 1000)

    if out_of_scope:
        fail_fast = True
        detected_conditions.append("implementation_write_scope_violation")
        if not failed_step:
            failed_step = "write_scope_validation"
    _append_transcript_item(
        transcript_path,
        step="write_scope_validation",
        command="validate write scope",
        exit_code=0 if not out_of_scope else 1,
        duration_ms=0,
        changed_paths=out_of_scope,
        status="pass" if not out_of_scope else "fail",
    )
    step_count += 1
    if len(write_set) > int(policy.get("implementation_max_files_touched", 0) or 0):
        fail_fast = True
        detected_conditions.append("implementation_files_touched_limit_exceeded")
    total_diff_lines = diff_line_count(before_allowed_texts, after_allowed_texts, changed_allowed)
    if total_diff_lines > int(policy.get("implementation_max_diff_lines", 0) or 0):
        fail_fast = True
        detected_conditions.append("implementation_diff_too_large")
        if not failed_step:
            failed_step = "diff_budget_validation"
    _append_transcript_item(
        transcript_path,
        step="diff_budget_validation",
        command="validate diff budget",
        exit_code=0 if total_diff_lines <= int(policy.get("implementation_max_diff_lines", 0) or 0) else 1,
        duration_ms=0,
        changed_paths=changed_allowed,
        status="pass" if total_diff_lines <= int(policy.get("implementation_max_diff_lines", 0) or 0) else "fail",
    )
    step_count += 1
    missing_checks = [item for item in required_checks if item not in checks_run]
    failed_checks = [item for item in required_checks if item not in checks_passed]
    if missing_checks:
        fail_fast = True
        detected_conditions.append("implementation_missing_check_execution")
    if failed_checks and bool(policy.get("implementation_require_all_checks_pass", True)):
        detected_conditions.append("implementation_required_checks_failed")
    if bool(policy.get("implementation_pause_on_partial_write", True)) and action_result.exit_code == 0 and not write_set:
        detected_conditions.append("implementation_partial_write")

    completed_execution = action_result.exit_code == 0 and "implementation_write_scope_violation" not in detected_conditions
    summary_bits = [f"implementation exit_code={action_result.exit_code}"]
    if write_set:
        summary_bits.append(f"writes={len(write_set)}")
    if checks_passed:
        summary_bits.append(f"checks_passed={len(checks_passed)}/{len(required_checks)}")

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
            "kind": "implementation",
            "name": decision["action"]["name"],
            "command": action_result.command,
            "args": dict(decision["action"].get("args", {})),
            "exit_code": action_result.exit_code,
            "stdout_excerpt": text_excerpt(action_result.stdout),
            "stderr_excerpt": text_excerpt(action_result.stderr),
            "stdout_json": {},
        },
        "artifacts": {
            "check_results": check_results,
            "implementation_workspace": str(workspace_path),
            "allowed_write_paths": allowed_write_paths,
            "out_of_scope_changes": out_of_scope,
            "diff_line_count": total_diff_lines,
            "execution_duration_ms": action_duration_ms,
            "checks_duration_ms": checks_duration_ms,
        },
        "machine_assessment": {
            "fail_fast": fail_fast,
            "completed_execution": completed_execution,
            "detected_conditions": detected_conditions,
        },
        "write_set": write_set,
        "checks_run": checks_run,
        "checks_passed": checks_passed,
        "transcript_path": str(transcript_path),
        "step_count": step_count,
        "failed_step": failed_step,
        "progress_delta": {
            "summary": "; ".join(summary_bits),
            "fingerprint": "|".join(write_set + checks_passed) if (write_set or checks_passed) else "implementation|no-progress",
        },
    }
