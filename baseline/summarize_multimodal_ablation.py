from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd

from baseline.common import REPO_ROOT, dump_json, ensure_dir, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize multimodal v2 ablation runs.")
    parser.add_argument("--runs-root", default="baseline/runs")
    parser.add_argument("--output-prefix", default="baseline/runs/multimodal_v2_ablation_summary")
    return parser.parse_args()


def _safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_run_summary(run_dir: Path) -> dict[str, Any] | None:
    summary_path = run_dir / "summary.json"
    metrics_path = run_dir / "evaluation" / "metrics_val.json"
    if not summary_path.exists() or not metrics_path.exists():
        return None
    import json

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    modalities = summary.get("modalities", {})
    row = {
        "run_dir": str(run_dir),
        "variant": str(summary.get("variant", run_dir.name.replace("multimodal_v2_", ""))),
        "seed": int(summary.get("seed", -1)),
        "modalities.sequence": bool(modalities.get("sequence", True)),
        "modalities.structure": bool(modalities.get("structure", False)),
        "modalities.context": bool(modalities.get("context", False)),
        "best_val_l1_macro_f1": float(_safe_get(metrics, "l1", "macro_f1", default=float("nan"))),
        "best_val_l2_macro_f1": float(_safe_get(metrics, "l2", "macro_f1", default=float("nan"))),
        "best_val_l3_macro_f1": float(_safe_get(metrics, "l3", "macro_f1", default=float("nan"))),
        "hierarchy_violation_rate": float(metrics.get("hierarchy_violation_rate", float("nan"))),
        "mean_gate_sequence": float(_safe_get(metrics, "mean_gates", "sequence", default=float("nan"))),
        "mean_gate_structure": float(_safe_get(metrics, "mean_gates", "structure", default=float("nan"))),
        "mean_gate_context": float(_safe_get(metrics, "mean_gates", "context", default=float("nan"))),
        "checkpoint_path": str(run_dir / "checkpoints" / "best.pt"),
    }
    return row


def classify_stability(deltas: list[float]) -> str:
    if len(deltas) < 3:
        return "insufficient_seeds"
    mean_delta = sum(deltas) / len(deltas)
    min_delta = min(deltas)
    better_count = sum(1 for x in deltas if x > 0.0)
    std_delta = math.sqrt(sum((x - mean_delta) ** 2 for x in deltas) / len(deltas))
    if better_count == len(deltas) and mean_delta >= 0.010 and min_delta > -0.005 and std_delta <= 0.015:
        return "stable_repeatable_gain"
    if mean_delta <= 0 or better_count <= 1 or min_delta <= -0.010:
        return "no_reliable_gain"
    return "weak_or_unstable_gain"


def main() -> None:
    args = parse_args()
    runs_root = resolve_path(args.runs_root, REPO_ROOT)
    output_prefix = resolve_path(args.output_prefix, REPO_ROOT)

    rows: list[dict[str, Any]] = []
    for run_dir in sorted(runs_root.glob("multimodal_v2*")):
        if not run_dir.is_dir():
            continue
        row = load_run_summary(run_dir)
        if row is not None:
            rows.append(row)

    if not rows:
        raise FileNotFoundError(f"No completed multimodal_v2 run summaries found under {runs_root}")

    df = pd.DataFrame(rows).sort_values(["variant", "seed", "run_dir"]).reset_index(drop=True)
    df["relative_to_seq_only_l3"] = float("nan")
    df["relative_to_ctx_handcrafted_l3"] = float("nan")
    df["stability_label"] = "insufficient_baseline"

    baseline_map = {
        int(row["seed"]): float(row["best_val_l3_macro_f1"])
        for _, row in df[df["variant"].isin(["stage1_seq_only", "seq_only"])].iterrows()
        if int(row["seed"]) >= 0
    }
    handcrafted_map = {
        int(row["seed"]): float(row["best_val_l3_macro_f1"])
        for _, row in df[df["variant"].isin(["seq_ctx", "seq_ctx_handcrafted"])].iterrows()
        if int(row["seed"]) >= 0
    }

    for idx, row in df.iterrows():
        seed = int(row["seed"])
        if seed in baseline_map:
            df.at[idx, "relative_to_seq_only_l3"] = float(row["best_val_l3_macro_f1"]) - baseline_map[seed]
        if seed in handcrafted_map:
            df.at[idx, "relative_to_ctx_handcrafted_l3"] = float(row["best_val_l3_macro_f1"]) - handcrafted_map[seed]

    for variant, variant_df in df.groupby("variant", sort=False):
        if variant in {"stage1_seq_only", "seq_only"}:
            df.loc[variant_df.index, "stability_label"] = "baseline"
            continue
        deltas = [float(x) for x in variant_df["relative_to_seq_only_l3"].tolist() if pd.notna(x)]
        label = classify_stability(deltas)
        df.loc[variant_df.index, "stability_label"] = label

    ensure_dir(output_prefix.parent)
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    df.to_csv(csv_path, index=False)
    dump_json(
        {
            "rows": df.to_dict(orient="records"),
            "variants": sorted(df["variant"].dropna().astype(str).unique().tolist()),
            "csv_path": str(csv_path),
        },
        json_path,
    )
    print(f"[ablation-summary] csv: {csv_path}")
    print(f"[ablation-summary] json: {json_path}")


if __name__ == "__main__":
    main()
