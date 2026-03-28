from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import REPO_ROOT, dump_json, load_yaml, now_ts, resolve_path


PHROG_RE = re.compile(r"^phrog_(\d+)$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build phold retrieval plan from local PHROG annotations.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    parser.add_argument("--target-status", default=None, help="Optional status override, e.g. trainable_core")
    return parser.parse_args()


def extract_phrog_id(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    m = PHROG_RE.match(text)
    if not m:
        return None
    return m.group(1)


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])

    wide_path = resolve_path(cfg["paths"]["training_labels_wide"], project_root)
    local_status_path = resolve_path(cfg["paths"]["all_exact_structure_status_tsv"], project_root)
    out_tsv = resolve_path(cfg["paths"]["phold_plan_tsv"], project_root)
    out_summary = resolve_path(cfg["paths"]["phold_plan_summary_json"], project_root)

    usecols = [
        "exact_sequence_rep_id",
        "sequence_length",
        "phrog_annotation",
        "status",
        "split",
        "homology_cluster_id",
    ]
    wide_df = pd.read_csv(wide_path, usecols=usecols, low_memory=False)
    wide_df["exact_sequence_rep_id"] = wide_df["exact_sequence_rep_id"].astype(str)
    if args.target_status:
        wide_df = wide_df[wide_df["status"] == args.target_status].copy()

    exact_df = (
        wide_df.groupby("exact_sequence_rep_id", as_index=False)
        .agg(
            sequence_length=("sequence_length", "first"),
            phrog_annotation=("phrog_annotation", "first"),
            any_trainable_core=("status", lambda s: bool((s == "trainable_core").any())),
            split_count=("split", "nunique"),
            homology_cluster_id=("homology_cluster_id", "first"),
        )
    )
    exact_df["phrog_id"] = exact_df["phrog_annotation"].map(extract_phrog_id)

    if local_status_path.exists():
        local_df = pd.read_csv(local_status_path, sep="\t", usecols=["exact_sequence_rep_id", "has_local_structure"], low_memory=False)
        local_df["exact_sequence_rep_id"] = local_df["exact_sequence_rep_id"].astype(str)
        exact_df = exact_df.merge(local_df, on="exact_sequence_rep_id", how="left")
        exact_df["has_local_structure"] = exact_df["has_local_structure"].fillna(False)
    else:
        exact_df["has_local_structure"] = False

    exact_df["needs_structure"] = ~exact_df["has_local_structure"]
    exact_df["candidate_for_phold_search"] = exact_df["phrog_id"].notna() & exact_df["needs_structure"]
    exact_df["phold_subarchive_name"] = exact_df["phrog_id"].map(
        lambda x: f"phrog_{int(x):05d}.tar.gz" if x is not None else None
    )

    plan_df = exact_df[exact_df["candidate_for_phold_search"]].copy()
    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    plan_df.to_csv(out_tsv, sep="\t", index=False, encoding="utf-8-sig")

    phrog_group_df = (
        plan_df.groupby("phrog_id", as_index=False)
        .agg(
            exact_sequence_count=("exact_sequence_rep_id", "count"),
            median_sequence_length=("sequence_length", "median"),
            any_trainable_core=("any_trainable_core", "max"),
            phold_subarchive_name=("phold_subarchive_name", "first"),
        )
        .sort_values(["exact_sequence_count", "phrog_id"], ascending=[False, True])
    )

    top_phrogs = phrog_group_df.head(20).to_dict(orient="records")
    summary = {
        "built_at": now_ts(),
        "input_training_labels": str(wide_path),
        "input_local_status": str(local_status_path),
        "output_plan_tsv": str(out_tsv),
        "target_status_filter": args.target_status,
        "all_exact_considered": int(len(exact_df)),
        "with_local_structure": int(exact_df["has_local_structure"].sum()),
        "needs_structure": int(exact_df["needs_structure"].sum()),
        "candidate_for_phold_search": int(plan_df["exact_sequence_rep_id"].nunique()),
        "candidate_unique_phrogs": int(plan_df["phrog_id"].nunique()),
        "top_phrogs": top_phrogs,
    }
    dump_json(summary, out_summary)

    print(f"[OK] phold retrieval plan saved: {out_tsv}")
    print(f"[OK] phold retrieval summary saved: {out_summary}")
    print(summary)


if __name__ == "__main__":
    main()
