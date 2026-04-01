from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import TASK_INDEX_PATH, TASK_REGISTRY_DIR


def task_registry_signature() -> str:
    digest = hashlib.sha256()
    paths: list[Path] = [TASK_INDEX_PATH]
    if TASK_REGISTRY_DIR.exists():
        paths.extend(sorted(TASK_REGISTRY_DIR.glob("*.json")))
    for path in paths:
        digest.update(str(path).encode("utf-8"))
        if path.exists():
            digest.update(str(path.stat().st_mtime_ns).encode("utf-8"))
        else:
            digest.update(b"missing")
    return digest.hexdigest()


def cooldown_ready_task_ids(task_records: list[dict[str, Any]], *, now_iso: str) -> list[str]:
    now = datetime.fromisoformat(now_iso)
    ready: list[str] = []
    for record in task_records:
        cooldown_until = str(record.get("cooldown_until", "")).strip()
        if not cooldown_until:
            continue
        try:
            cooldown_at = datetime.fromisoformat(cooldown_until)
        except ValueError:
            continue
        if cooldown_at <= now:
            ready.append(str(record.get("task_id", "")))
    return sorted(item for item in ready if item)


def wake_reason_for_cycle(
    *,
    has_eligible_task: bool,
    stale_available: bool,
    cooldown_ready_ids: list[str],
    registry_changed: bool,
    initial_boot: bool,
) -> str:
    if initial_boot:
        return "initial_boot"
    if stale_available:
        return "stale_takeover"
    if has_eligible_task and cooldown_ready_ids:
        return "retry_after_cooldown"
    if has_eligible_task and registry_changed:
        return "task_registry_changed"
    if has_eligible_task:
        return "eligible_task_found"
    return ""


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
