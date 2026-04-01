from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Produce a read-only closeout brief from run artifacts."
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[3]),
        help="Repository root path.",
    )
    parser.add_argument(
        "--run-dir",
        action="append",
        default=[],
        help="Run directory relative to repo root; may be repeated.",
    )
    parser.add_argument(
        "--runs-root",
        default="baseline/runs",
        help="Root for glob expansion when --glob is used.",
    )
    parser.add_argument(
        "--glob",
        default="",
        help="Optional glob under --runs-root to collect run directories.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--mode",
        choices=("summary_only", "strict_closeout"),
        default="summary_only",
        help="summary_only keeps missing artifacts as facts; strict_closeout turns missing required artifacts into non-zero exit.",
    )
    parser.add_argument(
        "--strict-required-artifacts",
        action="store_true",
        help="Backward-compatible alias for --mode strict_closeout.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else None


def _safe_get(d: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def build_gate_health_summary(metrics: dict[str, Any] | None) -> dict[str, Any]:
    thresholds = {
        "collapsed_sequence_gte": 0.95,
        "collapsed_structure_lte": 0.03,
        "collapsed_context_lte": 0.03,
        "warning_sequence_gte": 0.85,
    }
    metrics = metrics if isinstance(metrics, dict) else {}
    existing = metrics.get("gate_health")
    if isinstance(existing, dict):
        return existing

    mean_gates_raw = metrics.get("mean_gates")
    mean_gates = mean_gates_raw if isinstance(mean_gates_raw, dict) else {}
    multilabel_raw = metrics.get("multilabel")
    multilabel = multilabel_raw if isinstance(multilabel_raw, dict) else {}

    sequence = float(mean_gates.get("sequence", 0.0) or 0.0)
    structure = float(mean_gates.get("structure", 0.0) or 0.0)
    context = float(mean_gates.get("context", 0.0) or 0.0)
    multilabel_num_samples = int(multilabel.get("num_samples", 0) or 0)

    status = "healthy"
    reason_codes: list[str] = []
    if multilabel_num_samples <= 0:
        status = "warning"
        reason_codes.append("multilabel_num_samples_zero")
    if (
        sequence >= thresholds["collapsed_sequence_gte"]
        and structure <= thresholds["collapsed_structure_lte"]
        and context <= thresholds["collapsed_context_lte"]
    ):
        status = "collapsed"
        reason_codes.append("sequence_only_collapse")
    elif sequence >= thresholds["warning_sequence_gte"]:
        if status != "collapsed":
            status = "warning"
        reason_codes.append("sequence_dominant")

    return {
        "status": status,
        "mean_gates": {
            "sequence": sequence,
            "structure": structure,
            "context": context,
        },
        "multilabel_num_samples": multilabel_num_samples,
        "reason_codes": reason_codes,
        "thresholds": thresholds,
    }


def summarize_gate_health(metrics_val: dict[str, Any] | None, metrics_test: dict[str, Any] | None) -> dict[str, Any]:
    val_summary = build_gate_health_summary(metrics_val)
    test_summary = build_gate_health_summary(metrics_test)
    statuses = [val_summary["status"], test_summary["status"]]
    if "collapsed" in statuses:
        status = "collapsed"
    elif "warning" in statuses:
        status = "warning"
    else:
        status = "healthy"
    reason_codes = sorted(set(val_summary.get("reason_codes", []) + test_summary.get("reason_codes", [])))
    return {
        "status": status,
        "val": val_summary,
        "test": test_summary,
        "reason_codes": reason_codes,
    }


def collect_run(run_dir: Path) -> dict[str, Any]:
    summary = load_json(run_dir / "summary.json")
    history = load_json(run_dir / "logs" / "history.json")
    metrics_val = load_json(run_dir / "evaluation" / "metrics_val.json")
    metrics_test = load_json(run_dir / "evaluation" / "metrics_test.json")

    missing = []
    for rel in ("summary.json", "logs/history.json", "evaluation/metrics_val.json", "evaluation/metrics_test.json"):
        if not (run_dir / rel).exists():
            missing.append(rel)

    train_rows = _safe_get(history, "train", default=[])
    val_rows = _safe_get(history, "val", default=[])
    train_last = train_rows[-1] if isinstance(train_rows, list) and train_rows else {}
    val_last = val_rows[-1] if isinstance(val_rows, list) and val_rows else {}

    required_artifacts = (
        "summary.json",
        "logs/history.json",
        "evaluation/metrics_val.json",
        "evaluation/metrics_test.json",
    )
    present_artifacts = [rel for rel in required_artifacts if (run_dir / rel).exists()]
    artifact_status = "complete" if not missing else "incomplete"
    gate_health = summarize_gate_health(metrics_val, metrics_test)

    return {
        "run_dir": str(run_dir),
        "run_name": _safe_get(summary, "run_name", default=run_dir.name),
        "variant": _safe_get(summary, "variant", default=""),
        "seed": _safe_get(summary, "seed", default=""),
        "best_val_l3_macro_f1": _safe_get(summary, "best_val_l3_macro_f1", default=None),
        "summary_timing_last_train": _safe_get(summary, "timing", "last_train", default={}),
        "summary_timing_last_val": _safe_get(summary, "timing", "last_val", default={}),
        "train_last": train_last if isinstance(train_last, dict) else {},
        "val_last": val_last if isinstance(val_last, dict) else {},
        "metrics_val": metrics_val or {},
        "metrics_test": metrics_test or {},
        "artifacts_required": list(required_artifacts),
        "artifacts_present": present_artifacts,
        "missing_artifacts": missing,
        "artifact_status": artifact_status,
        "gate_health": gate_health,
    }


def enrich_record(record: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(record)
    if not isinstance(enriched.get("gate_health"), dict):
        enriched["gate_health"] = summarize_gate_health(
            enriched.get("metrics_val") if isinstance(enriched.get("metrics_val"), dict) else {},
            enriched.get("metrics_test") if isinstance(enriched.get("metrics_test"), dict) else {},
        )
    return enriched


def fmt_num(value: Any, digits: int = 6) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    return "n/a"


def build_markdown(records: list[dict[str, Any]], mode: str = "summary_only") -> str:
    records = [enrich_record(record) for record in records]
    lines: list[str] = []
    lines.append("# results-closeout-lite brief")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Read-only artifact extraction.")
    lines.append("- No default switch, upgrade, promote, or demote conclusions.")
    lines.append(f"- closeout mode: `{mode}`")
    lines.append("")

    for rec in records:
        lines.append(f"## Run: `{rec['run_name']}`")
        lines.append(f"- run_dir: `{rec['run_dir']}`")
        lines.append(f"- variant: `{rec.get('variant', '')}`")
        lines.append(f"- seed: `{rec.get('seed', '')}`")
        lines.append(f"- best_val_l3_macro_f1 (summary): `{fmt_num(rec.get('best_val_l3_macro_f1'))}`")

        train_timing = rec.get("summary_timing_last_train", {})
        val_timing = rec.get("summary_timing_last_val", {})
        lines.append("- summary timing (last_train):")
        lines.append(f"  - data_wait_ms: `{fmt_num(_safe_get(train_timing, 'data_wait_ms'))}`")
        lines.append(f"  - step_ms: `{fmt_num(_safe_get(train_timing, 'step_ms'))}`")
        lines.append("- summary timing (last_val):")
        lines.append(f"  - data_wait_ms: `{fmt_num(_safe_get(val_timing, 'data_wait_ms'))}`")
        lines.append(f"  - step_ms: `{fmt_num(_safe_get(val_timing, 'step_ms'))}`")

        metrics_val = rec.get("metrics_val", {})
        metrics_test = rec.get("metrics_test", {})
        gate_health = rec.get("gate_health", {})
        lines.append(f"- artifact_status: `{rec.get('artifact_status', 'unknown')}`")
        lines.append("- evaluation metrics (val):")
        lines.append(f"  - l1_macro_f1: `{fmt_num(_safe_get(metrics_val, 'l1', 'macro_f1'))}`")
        lines.append(f"  - l2_macro_f1: `{fmt_num(_safe_get(metrics_val, 'l2', 'macro_f1'))}`")
        lines.append(f"  - l3_macro_f1: `{fmt_num(_safe_get(metrics_val, 'l3', 'macro_f1'))}`")
        lines.append("- evaluation metrics (test):")
        lines.append(f"  - l1_macro_f1: `{fmt_num(_safe_get(metrics_test, 'l1', 'macro_f1'))}`")
        lines.append(f"  - l2_macro_f1: `{fmt_num(_safe_get(metrics_test, 'l2', 'macro_f1'))}`")
        lines.append(f"  - l3_macro_f1: `{fmt_num(_safe_get(metrics_test, 'l3', 'macro_f1'))}`")
        lines.append(f"- gate_health: `{_safe_get(gate_health, 'status', default='unknown')}`")
        lines.append("- gate_health (val):")
        lines.append(f"  - status: `{_safe_get(gate_health, 'val', 'status', default='unknown')}`")
        lines.append(f"  - multilabel_num_samples: `{fmt_num(_safe_get(gate_health, 'val', 'multilabel_num_samples'))}`")
        lines.append(f"  - sequence: `{fmt_num(_safe_get(gate_health, 'val', 'mean_gates', 'sequence'))}`")
        lines.append(f"  - structure: `{fmt_num(_safe_get(gate_health, 'val', 'mean_gates', 'structure'))}`")
        lines.append(f"  - context: `{fmt_num(_safe_get(gate_health, 'val', 'mean_gates', 'context'))}`")
        lines.append("- gate_health (test):")
        lines.append(f"  - status: `{_safe_get(gate_health, 'test', 'status', default='unknown')}`")
        lines.append(f"  - multilabel_num_samples: `{fmt_num(_safe_get(gate_health, 'test', 'multilabel_num_samples'))}`")
        lines.append(f"  - sequence: `{fmt_num(_safe_get(gate_health, 'test', 'mean_gates', 'sequence'))}`")
        lines.append(f"  - structure: `{fmt_num(_safe_get(gate_health, 'test', 'mean_gates', 'structure'))}`")
        lines.append(f"  - context: `{fmt_num(_safe_get(gate_health, 'test', 'mean_gates', 'context'))}`")

        missing = rec.get("missing_artifacts", [])
        if missing:
            lines.append("- missing_artifacts:")
            for item in missing:
                lines.append(f"  - `{item}`")
        else:
            lines.append("- missing_artifacts: none")
        lines.append("")

    lines.append("## 需人工判定")
    lines.append("- 本报告仅提取事实与结构化摘要。")
    lines.append("- 是否切默认、是否窗口升级、是否 promote/demote 需人工判定。")
    return "\n".join(lines).strip() + "\n"


def compute_status(records: list[dict[str, Any]], strict_mode: bool) -> str:
    has_missing = any(bool(record.get("missing_artifacts")) for record in records)
    if strict_mode and has_missing:
        return "strict_fail"
    if has_missing:
        return "soft_missing"
    return "ok"


def build_payload(records: list[dict[str, Any]], strict_mode: bool) -> dict[str, Any]:
    mode = "strict_closeout" if strict_mode else "summary_only"
    enriched_records = [enrich_record(record) for record in records]
    return {
        "schema_version": 1,
        "tool_name": "results-closeout-lite",
        "status": compute_status(enriched_records, strict_mode=strict_mode),
        "mode": mode,
        "strict_mode": strict_mode,
        "artifact_contract": {
            "required": [
                "summary.json",
                "logs/history.json",
                "evaluation/metrics_val.json",
                "evaluation/metrics_test.json",
            ],
            "missing_behavior": "strict_fail" if strict_mode else "soft_missing",
        },
        "scope": {
            "read_only_artifact_extraction": True,
            "forbidden_automatic_decisions": [
                "default switch recommendation",
                "window upgrade recommendation",
                "promote conclusion",
                "demote conclusion",
            ],
        },
        "runs": enriched_records,
        "manual_decision_required": [
            "本报告仅提取事实与结构化摘要。",
            "是否切默认、是否窗口升级、是否 promote/demote 需人工判定。",
        ],
    }


def resolve_run_dirs(repo_root: Path, run_dirs: list[str], runs_root: str, glob_pattern: str) -> list[Path]:
    resolved: list[Path] = []
    for run_dir in run_dirs:
        path = Path(run_dir)
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        resolved.append(path)

    if glob_pattern:
        root = Path(runs_root)
        if not root.is_absolute():
            root = (repo_root / root).resolve()
        resolved.extend(sorted(p for p in root.glob(glob_pattern) if p.is_dir()))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in resolved:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    strict_mode = bool(args.strict_required_artifacts or args.mode == "strict_closeout")

    run_paths = resolve_run_dirs(
        repo_root=repo_root,
        run_dirs=args.run_dir,
        runs_root=args.runs_root,
        glob_pattern=args.glob,
    )
    if not run_paths:
        print("[error] no run directories provided. Use --run-dir or --glob.")
        return 1

    records = []
    missing_dirs = []
    for run_path in run_paths:
        if not run_path.exists():
            missing_dirs.append(str(run_path))
            continue
        records.append(collect_run(run_path))

    if missing_dirs:
        print("[error] missing run directories:")
        for item in missing_dirs:
            print(f"- {item}")
        return 1

    strict_failure = strict_mode and any(
        bool(record.get("missing_artifacts")) for record in records
    )

    if args.format == "json":
        print(json.dumps(build_payload(records, strict_mode=strict_mode), ensure_ascii=False, indent=2))
    else:
        report = build_markdown(records, mode="strict_closeout" if strict_mode else "summary_only")
        print(report, end="")

    return 1 if strict_failure else 0


if __name__ == "__main__":
    sys.exit(main())
