from __future__ import annotations

from typing import Any


def evaluate_regression(
    *,
    gate_health: dict[str, Any] | None = None,
    mean_gates: dict[str, Any] | None = None,
    closeout_status: str = "",
    required_artifacts_ok: bool = True,
    current_multilabel_micro_f1: float | None = None,
    best_known_multilabel_micro_f1: float | None = None,
) -> dict[str, Any]:
    gate_health = dict(gate_health or {})
    mean_gates = dict(mean_gates or {})
    if str(gate_health.get("status", "")) == "collapsed":
        return {
            "regression_detected": True,
            "regression_reason_code": "gate_collapse_detected",
            "regression_summary": "gate health collapsed",
            "recommended_action": "pause lane and inspect gate health evidence",
        }

    sequence_gate = float(mean_gates.get("sequence", 0.0) or 0.0)
    structure_gate = float(mean_gates.get("structure", 0.0) or 0.0)
    context_gate = float(mean_gates.get("context", 0.0) or 0.0)
    if sequence_gate >= 0.95:
        return {
            "regression_detected": True,
            "regression_reason_code": "sequence_gate_dominance",
            "regression_summary": "sequence gate dominance exceeded threshold",
            "recommended_action": "pause lane and compare against best-known gate balance",
        }
    if (structure_gate + context_gate) <= 0.05:
        return {
            "regression_detected": True,
            "regression_reason_code": "structure_context_starved",
            "regression_summary": "structure/context contribution fell below threshold",
            "recommended_action": "pause lane and inspect multimodal contribution",
        }
    if closeout_status == "failed":
        return {
            "regression_detected": True,
            "regression_reason_code": "strict_closeout_failed",
            "regression_summary": "strict closeout reported failure",
            "recommended_action": "pause lane and inspect closeout report",
        }
    if not required_artifacts_ok:
        return {
            "regression_detected": True,
            "regression_reason_code": "required_artifacts_missing",
            "regression_summary": "required artifacts are missing",
            "recommended_action": "pause lane and repair artifacts before continuing",
        }
    if (
        current_multilabel_micro_f1 is not None
        and best_known_multilabel_micro_f1 is not None
        and current_multilabel_micro_f1 < best_known_multilabel_micro_f1 - 0.10
    ):
        return {
            "regression_detected": True,
            "regression_reason_code": "multilabel_metric_regression",
            "regression_summary": "multilabel micro_f1 regressed materially from best-known evidence",
            "recommended_action": "pause lane and verify whether the regression is expected",
        }
    return {
        "regression_detected": False,
        "regression_reason_code": "",
        "regression_summary": "",
        "recommended_action": "",
    }
