from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from integrations.codex_loop.constants import EVENTS_PATH
from integrations.codex_loop.schemas import ensure_parent


def append_event(
    event_type: str,
    *,
    runner_id: str = "",
    task_id: str = "",
    run_id: str = "",
    state_status: str = "",
    details: dict[str, Any] | None = None,
    reason_code: str = "",
    suggested_next_actions: list[str] | None = None,
) -> None:
    ensure_parent(EVENTS_PATH)
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event_type": event_type,
        "runner_id": runner_id,
        "task_id": task_id,
        "run_id": run_id,
        "state_status": state_status,
        "reason_code": reason_code,
        "suggested_next_actions": list(suggested_next_actions or []),
        "details": details or {},
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
