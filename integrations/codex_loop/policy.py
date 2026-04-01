from __future__ import annotations

from integrations.codex_loop.constants import DEFAULT_INTERVENTION_POLICY, INTERVENTION_POLICY_PATH
from integrations.codex_loop.schemas import load_json, validate_intervention_policy


def load_policy() -> dict:
    if not INTERVENTION_POLICY_PATH.exists():
        return validate_intervention_policy(DEFAULT_INTERVENTION_POLICY).data
    merged = dict(DEFAULT_INTERVENTION_POLICY)
    merged.update(load_json(INTERVENTION_POLICY_PATH))
    return validate_intervention_policy(merged).data
