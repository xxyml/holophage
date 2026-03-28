from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import REPO_ROOT, dump_json, load_yaml, now_ts, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build exact-sequence structure gap manifests.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])

    wide_path = resolve_path(cfg["paths"]["training_labels_wide"], project_root)
    local_manifest_path = resolve_path(cfg["paths"]["local_structure_manifest_tsv"], project_root)
    out_all_status = resolve_path(cfg["paths"]["all_exact_structure_status_tsv"], project_root)
    out_missing_all = resolve_path(cfg["paths"]["missing_exact_all_tsv"], project_root)
    out_missing_core = resolve_path(cfg["paths"]["missing_exact_trainable_core_tsv"], project_root)
    summary_json = resolve_path(cfg["paths"]["missing_exact_summary_json"], project_root)

    usecols = [
        "exact_sequence_rep_id",
        "sequence",
        "sequence_length",
        "status",
        "split",
        "homology_cluster_id",
        "node_primary",
        "level1_label",
        "level2_label",
    ]
    wide_df = pd.read_csv(wide_path, usecols=usecols, low_memory=False)
    wide_df["exact_sequence_rep_id"] = wide_df["exact_sequence_rep_id"].astype(str)

    grouped = (
        wide_df.groupby("exact_sequence_rep_id", as_index=False)
        .agg(
            sequence=("sequence", "first"),
            sequence_length=("sequence_length", "first"),
            homology_cluster_id=("homology_cluster_id", "first"),
            any_trainable_core=("status", lambda s: bool((s == "trainable_core").any())),
            split_count=("split", "nunique"),
        )
    )

    level_df = wide_df[["exact_sequence_rep_id", "node_primary", "level1_label", "level2_label"]].drop_duplicates()
    grouped = grouped.merge(
        level_df.groupby("exact_sequence_rep_id", as_index=False)
        .agg(
            node_primary=("node_primary", lambda s: "|".join(sorted({str(x) for x in s.dropna() if str(x)}))),
            level1_label=("level1_label", lambda s: "|".join(sorted({str(x) for x in s.dropna() if str(x)}))),
            level2_label=("level2_label", lambda s: "|".join(sorted({str(x) for x in s.dropna() if str(x)}))),
        ),
        on="exact_sequence_rep_id",
        how="left",
    )

    if local_manifest_path.exists():
        local_df = pd.read_csv(local_manifest_path, sep="\t", low_memory=False)
        local_exact = (
            local_df.dropna(subset=["exact_sequence_rep_id"])
            .groupby("exact_sequence_rep_id", as_index=False)
            .agg(
                local_structure_count=("structure_path", "count"),
                local_structure_sources=("source_name", lambda s: "|".join(sorted({str(x) for x in s.dropna() if str(x)}))),
                local_confidence_scales=("confidence_scale", lambda s: "|".join(sorted({str(x) for x in s.dropna() if str(x)}))),
            )
        )
    else:
        local_exact = pd.DataFrame(columns=["exact_sequence_rep_id", "local_structure_count", "local_structure_sources", "local_confidence_scales"])

    grouped = grouped.merge(local_exact, on="exact_sequence_rep_id", how="left")
    grouped["local_structure_count"] = grouped["local_structure_count"].fillna(0).astype(int)
    grouped["has_local_structure"] = grouped["local_structure_count"] > 0
    grouped["built_at"] = now_ts()

    missing_all = grouped[~grouped["has_local_structure"]].copy()
    missing_core = grouped[(grouped["any_trainable_core"]) & (~grouped["has_local_structure"])].copy()

    out_all_status.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_csv(out_all_status, sep="\t", index=False, encoding="utf-8-sig")
    missing_all.to_csv(out_missing_all, sep="\t", index=False, encoding="utf-8-sig")
    missing_core.to_csv(out_missing_core, sep="\t", index=False, encoding="utf-8-sig")

    summary = {
        "built_at": now_ts(),
        "input_training_labels": str(wide_path),
        "input_local_manifest": str(local_manifest_path),
        "output_all_exact_status_tsv": str(out_all_status),
        "output_missing_all_tsv": str(out_missing_all),
        "output_missing_trainable_core_tsv": str(out_missing_core),
        "all_exact_total": int(len(grouped)),
        "all_exact_with_local_structure": int(grouped["has_local_structure"].sum()),
        "all_exact_missing_structure": int(len(missing_all)),
        "trainable_core_exact_total": int(grouped["any_trainable_core"].sum()),
        "trainable_core_exact_with_local_structure": int(grouped["any_trainable_core"].sum() - len(missing_core)),
        "trainable_core_exact_missing_structure": int(len(missing_core)),
    }
    dump_json(summary, summary_json)

    print(f"[OK] all exact structure status saved: {out_all_status}")
    print(f"[OK] missing exact (all) saved: {out_missing_all}")
    print(f"[OK] missing exact (trainable_core) saved: {out_missing_core}")
    print(f"[OK] summary saved: {summary_json}")
    print(summary)


if __name__ == "__main__":
    main()
