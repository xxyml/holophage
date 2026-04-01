from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from integrations.codex_loop.constants import REPO_ROOT
from integrations.codex_loop.schemas import load_json


def text_excerpt(text: str, max_lines: int = 12, max_chars: int = 1200) -> str:
    normalized_lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    excerpt = "\n".join(normalized_lines[:max_lines])
    if len(excerpt) > max_chars:
        return excerpt[: max_chars - 3] + "..."
    return excerpt


def parse_json_output(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    decoder = json.JSONDecoder()
    for idx, char in enumerate(stripped):
        if char not in "{[":
            continue
        try:
            payload, end = decoder.raw_decode(stripped[idx:])
        except json.JSONDecodeError:
            continue
        remainder = stripped[idx + end :].strip()
        if remainder:
            continue
        return payload if isinstance(payload, dict) else None
    return None


def _resolve_path(raw_path: str | None, default_relative: str) -> Path:
    if raw_path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (REPO_ROOT / path).resolve()
    return (REPO_ROOT / default_relative).resolve()


def _lookup_arg(action_args: dict[str, Any], key: str) -> str | None:
    value = action_args.get(key)
    if isinstance(value, str):
        return value
    return None


def collect_governance_artifacts(action_args: dict[str, Any]) -> dict[str, Any]:
    output_dir = _resolve_path(
        raw_path=_lookup_arg(action_args, "output_dir"),
        default_relative="data_processed/governance",
    )
    summary_path = output_dir / "pfo_v1_0_2_governance_summary.json"
    summary = None
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "summary_file": str(summary_path),
        "summary_exists": summary_path.exists(),
        "governance_summary": summary,
    }


def collect_results_closeout_artifacts(stdout_json: dict[str, Any] | None) -> dict[str, Any]:
    runs = stdout_json.get("runs", []) if isinstance(stdout_json, dict) else []
    gate_health_by_run: dict[str, Any] = {}
    dual_output_by_run: dict[str, Any] = {}
    if isinstance(runs, list):
        for item in runs:
            if not isinstance(item, dict):
                continue
            run_name = str(item.get("run_name") or item.get("run_dir") or "")
            if not run_name:
                continue
            gate_health_by_run[run_name] = item.get("gate_health", {})
            dual_output_by_run[run_name] = item.get("dual_output_runtime", {})
    return {
        "runs_count": len(runs) if isinstance(runs, list) else 0,
        "closeout_status": stdout_json.get("status") if isinstance(stdout_json, dict) else None,
        "gate_health_by_run": gate_health_by_run,
        "dual_output_by_run": dual_output_by_run,
    }


def collect_multilabel_audit_artifacts(stdout_json: dict[str, Any] | None) -> dict[str, Any]:
    checks = stdout_json.get("checks", []) if isinstance(stdout_json, dict) else []
    fail_items = []
    warn_items = []
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "")).upper()
            name = str(item.get("name", ""))
            if status == "FAIL":
                fail_items.append(name)
            elif status == "WARN":
                warn_items.append(name)
    return {
        "audit_fail_items": fail_items,
        "audit_warn_items": warn_items,
        "audit_fail_count": len(fail_items),
        "audit_warn_count": len(warn_items),
    }


def collect_truth_calibration_artifacts(stdout_json: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "truth_status": stdout_json.get("status") if isinstance(stdout_json, dict) else None,
        "conflicts": stdout_json.get("conflicts") if isinstance(stdout_json, dict) else None,
    }


def collect_task_artifacts(task_type: str, action_args: dict[str, Any], stdout_json: dict[str, Any] | None) -> dict[str, Any]:
    if task_type == "governance_refresh":
        return collect_governance_artifacts(action_args)
    if task_type == "results_closeout":
        return collect_results_closeout_artifacts(stdout_json)
    if task_type == "multilabel_readiness_audit":
        return collect_multilabel_audit_artifacts(stdout_json)
    if task_type == "truth_calibration":
        return collect_truth_calibration_artifacts(stdout_json)
    return {}


def _safe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _best_val_multilabel_micro(summary: dict[str, Any]) -> float | None:
    best_val_metrics = summary.get("best_val_metrics", {})
    if not isinstance(best_val_metrics, dict):
        return None
    multilabel = best_val_metrics.get("multilabel", {})
    if not isinstance(multilabel, dict):
        return None
    return _safe_float(multilabel.get("micro_f1"))


def _mean_gates(summary: dict[str, Any]) -> dict[str, Any]:
    best_val_metrics = summary.get("best_val_metrics", {})
    if not isinstance(best_val_metrics, dict):
        return {}
    mean_gates = best_val_metrics.get("mean_gates", {})
    return mean_gates if isinstance(mean_gates, dict) else {}


def _gate_health(summary: dict[str, Any]) -> dict[str, Any]:
    best_val_metrics = summary.get("best_val_metrics", {})
    if not isinstance(best_val_metrics, dict):
        return {}
    gate_health = best_val_metrics.get("gate_health", {})
    return gate_health if isinstance(gate_health, dict) else {}


def _dual_output_runtime(summary: dict[str, Any], metrics_path: Path | None = None) -> dict[str, Any]:
    dual_output_runtime = summary.get("dual_output_runtime", {})
    if isinstance(dual_output_runtime, dict) and dual_output_runtime:
        return dual_output_runtime
    if metrics_path and metrics_path.exists():
        metrics = load_json(metrics_path)
        dual_output = metrics.get("dual_output", {})
        if isinstance(dual_output, dict):
            return {
                "enabled": bool(dual_output.get("multilabel_head_present", False)),
                "protocol": str(dual_output.get("protocol", "")),
                "metrics_masked_by_target_mask": bool(dual_output.get("metrics_masked_by_target_mask", True)),
            }
    return {"enabled": False, "protocol": "", "metrics_masked_by_target_mask": True}


def build_experiment_registry_draft(run_dir: Path, task_id: str, config_path: str | None = None) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    summary_path = run_dir / "summary.json"
    summary = load_json(summary_path) if summary_path.exists() else {}
    metrics_val_path = run_dir / "evaluation" / "metrics_val.json"
    metrics_test_path = run_dir / "evaluation" / "metrics_test.json"

    run_name = str(summary.get("run_name") or run_dir.name)
    seed = summary.get("seed")
    experiment_id = run_name if seed in (None, "", 0) else f"{run_name}__seed{seed}"

    closeout_artifacts = summary.get("closeout_artifacts", {})
    closeout_status = "passed" if metrics_val_path.exists() and metrics_test_path.exists() else "pending"
    if isinstance(closeout_artifacts, dict) and closeout_artifacts.get("exported") is True:
        closeout_status = "ready" if closeout_status == "pending" else closeout_status

    return {
        "experiment_id": experiment_id,
        "task_id": task_id,
        "run_dir": str(run_dir),
        "summary_path": str(summary_path),
        "config_path": config_path or "",
        "variant": str(summary.get("variant") or run_name),
        "seed": seed if isinstance(seed, (int, str)) else "",
        "status": "candidate",
        "closeout_status": closeout_status,
        "best_epoch": _safe_int(summary.get("best_epoch")),
        "best_val_l3_macro_f1": _safe_float(summary.get("best_val_l3_macro_f1")),
        "best_val_multilabel_micro_f1": _best_val_multilabel_micro(summary),
        "mean_gates": _mean_gates(summary),
        "gate_health": _gate_health(summary),
        "metrics_val_path": str(metrics_val_path) if metrics_val_path.exists() else "",
        "metrics_test_path": str(metrics_test_path) if metrics_test_path.exists() else "",
        "review_verdict": "",
        "last_verified_at": "",
        "run_name": run_name,
        "modalities": summary.get("modalities", {}) if isinstance(summary.get("modalities"), dict) else {},
        "multilabel_head": summary.get("multilabel_head", {}) if isinstance(summary.get("multilabel_head"), dict) else {},
        "prepack": summary.get("prepack", {}) if isinstance(summary.get("prepack"), dict) else {},
        "epochs": _safe_int(summary.get("epochs")),
        "train_samples": _safe_int(summary.get("train_samples")),
        "val_samples": _safe_int(summary.get("val_samples")),
        "dataloader": summary.get("dataloader", {}) if isinstance(summary.get("dataloader"), dict) else {},
        "timing": summary.get("timing", {}) if isinstance(summary.get("timing"), dict) else {},
        "closeout_artifacts": closeout_artifacts if isinstance(closeout_artifacts, dict) else {},
        "dual_output_runtime": _dual_output_runtime(summary, metrics_path=metrics_val_path if metrics_val_path.exists() else None),
    }
