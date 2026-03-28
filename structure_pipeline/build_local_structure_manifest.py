from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import REPO_ROOT, dump_json, load_yaml, now_ts, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build manifest for local structure assets.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    parser.add_argument("--limit-per-source", type=int, default=None, help="Optional debug limit per local source.")
    return parser.parse_args()


def scan_local_source(source_cfg: dict[str, str], training_map: pd.DataFrame, limit_per_source: int | None) -> list[dict[str, object]]:
    root = resolve_path(source_cfg["path"])
    suffix = f".{source_cfg.get('format', 'pdb').lower().lstrip('.')}"
    files = sorted(root.rglob(f"*{suffix}"))
    if limit_per_source is not None:
        files = files[:limit_per_source]

    rows: list[dict[str, object]] = []
    for file_path in files:
        protein_id = file_path.stem
        row = {
            "source_name": source_cfg["name"],
            "source_root": str(root),
            "structure_path": str(file_path),
            "structure_format": source_cfg.get("format", "pdb"),
            "confidence_scale": source_cfg.get("confidence_scale", "unknown"),
            "protein_id": protein_id,
        }
        rows.append(row)

    source_df = pd.DataFrame(rows)
    if source_df.empty:
        return []

    source_df = source_df.merge(training_map, on="protein_id", how="left")
    source_df["matched_training_protein"] = source_df["exact_sequence_rep_id"].notna()
    source_df["matched_trainable_core"] = source_df["status"].eq("trainable_core")
    source_df["built_at"] = now_ts()
    return source_df.to_dict(orient="records")


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])

    wide_path = resolve_path(cfg["paths"]["training_labels_wide"], project_root)
    out_tsv = resolve_path(cfg["paths"]["local_structure_manifest_tsv"], project_root)
    summary_json = resolve_path(cfg["paths"]["local_structure_coverage_summary_json"], project_root)

    usecols = [
        "protein_id",
        "exact_sequence_rep_id",
        "split",
        "status",
        "sequence_length",
        "homology_cluster_id",
        "node_primary",
        "level1_label",
        "level2_label",
    ]
    training_df = pd.read_csv(wide_path, usecols=usecols, low_memory=False)
    training_df["protein_id"] = training_df["protein_id"].astype(str)

    all_rows: list[dict[str, object]] = []
    for source_cfg in cfg["sources"].get("local_pdb", {}).get("directories", []):
        all_rows.extend(scan_local_source(source_cfg, training_df, args.limit_per_source))

    manifest_df = pd.DataFrame(all_rows)
    if manifest_df.empty:
        manifest_df = pd.DataFrame(
            columns=[
                "source_name",
                "source_root",
                "structure_path",
                "structure_format",
                "confidence_scale",
                "protein_id",
                "exact_sequence_rep_id",
                "split",
                "status",
                "sequence_length",
                "homology_cluster_id",
                "node_primary",
                "level1_label",
                "level2_label",
                "matched_training_protein",
                "matched_trainable_core",
                "built_at",
            ]
        )

    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    manifest_df.to_csv(out_tsv, sep="\t", index=False, encoding="utf-8-sig")

    summary: dict[str, object] = {
        "built_at": now_ts(),
        "input_training_labels": str(wide_path),
        "output_manifest_tsv": str(out_tsv),
        "row_count": int(len(manifest_df)),
        "matched_training_protein_count": int(manifest_df["matched_training_protein"].sum()) if not manifest_df.empty else 0,
        "matched_trainable_core_count": int(manifest_df["matched_trainable_core"].sum()) if not manifest_df.empty else 0,
        "source_summaries": [],
    }

    if not manifest_df.empty:
        all_exact_total = int(training_df["exact_sequence_rep_id"].nunique())
        core_df = training_df[training_df["status"] == "trainable_core"].copy()
        core_exact_total = int(core_df["exact_sequence_rep_id"].nunique())
        summary["all_exact_total"] = all_exact_total
        summary["trainable_core_exact_total"] = core_exact_total

        for source_name, sub in manifest_df.groupby("source_name", dropna=False):
            source_summary = {
                "source_name": source_name,
                "file_count": int(len(sub)),
                "matched_training_protein_count": int(sub["matched_training_protein"].sum()),
                "matched_trainable_core_count": int(sub["matched_trainable_core"].sum()),
                "matched_exact_count": int(sub["exact_sequence_rep_id"].dropna().nunique()),
                "matched_trainable_core_exact_count": int(
                    sub.loc[sub["matched_trainable_core"], "exact_sequence_rep_id"].dropna().nunique()
                ),
                "confidence_scales": sorted(sub["confidence_scale"].dropna().astype(str).unique().tolist()),
            }
            summary["source_summaries"].append(source_summary)

        summary["union_exact_count"] = int(manifest_df["exact_sequence_rep_id"].dropna().nunique())
        summary["union_trainable_core_exact_count"] = int(
            manifest_df.loc[manifest_df["matched_trainable_core"], "exact_sequence_rep_id"].dropna().nunique()
        )
        summary["union_trainable_core_exact_fraction"] = round(
            summary["union_trainable_core_exact_count"] / core_exact_total, 6
        ) if core_exact_total else 0.0

    dump_json(summary, summary_json)

    print(f"[OK] local structure manifest saved: {out_tsv}")
    print(f"[OK] local structure coverage summary saved: {summary_json}")
    print(summary)


if __name__ == "__main__":
    main()
