from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from structure_pipeline.common import (
    REPO_ROOT,
    dump_json,
    infer_afdb_entry_id,
    infer_genbank_accession,
    infer_uniprot_accession,
    load_optional_hints,
    load_yaml,
    now_ts,
    resolve_path,
    sha256_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build exact-sequence structure target manifest.")
    parser.add_argument("--config", default="structure_pipeline/config.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for smoke runs.")
    return parser.parse_args()


def merge_hints(targets: pd.DataFrame, hints: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "candidate_uniprot_accession",
        "candidate_afdb_entry_id",
        "candidate_bfvd_model_id",
        "candidate_viro3d_identifier",
        "candidate_viro3d_qualifier",
    ]
    for column in columns:
        if column not in targets.columns:
            targets[column] = None

    if hints is None or hints.empty:
        return targets

    if "exact_sequence_rep_id" not in hints.columns:
        raise ValueError("Hints file missing required column: exact_sequence_rep_id")

    hints = hints.copy()
    for column in columns:
        if column not in hints.columns:
            hints[column] = None

    merged = targets.merge(
        hints[["exact_sequence_rep_id", *columns]],
        on="exact_sequence_rep_id",
        how="left",
        suffixes=("", "_hint"),
    )
    for column in columns:
        hint_col = f"{column}_hint"
        merged[column] = merged[hint_col].combine_first(merged[column])
        merged.drop(columns=[hint_col], inplace=True)
    return merged


def infer_candidates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["candidate_uniprot_accession"] = df["exact_sequence_rep_id"].map(infer_uniprot_accession)
    df["candidate_afdb_entry_id"] = df["exact_sequence_rep_id"].map(infer_afdb_entry_id)
    df["candidate_bfvd_model_id"] = None
    df["candidate_viro3d_identifier"] = df["exact_sequence_rep_id"].map(infer_genbank_accession)
    df["candidate_viro3d_qualifier"] = df["candidate_viro3d_identifier"].map(lambda x: "genbank_id" if x else None)
    return df


def main() -> None:
    args = parse_args()
    cfg = load_yaml(resolve_path(args.config, REPO_ROOT))
    project_root = resolve_path(cfg["project_root"])
    wide_path = resolve_path(cfg["paths"]["training_labels_wide"], project_root)
    out_tsv = resolve_path(cfg["paths"]["target_manifest_tsv"], project_root)
    out_parquet = resolve_path(cfg["paths"]["target_manifest_parquet"], project_root)
    summary_json = out_tsv.parent / "structure_target_manifest.summary.json"
    hints_path = resolve_path(cfg["paths"]["hints_tsv"], project_root)

    usecols = [
        "exact_sequence_rep_id",
        "sequence",
        "sequence_length",
        "status",
        "node_primary",
        "level1_label",
        "level2_label",
        "homology_cluster_id",
    ]
    df = pd.read_csv(wide_path, usecols=usecols, low_memory=False)
    df = df[df["status"] == cfg["screening"]["target_status"]].copy()
    df = df.drop_duplicates("exact_sequence_rep_id", keep="first")
    if args.limit:
        df = df.head(args.limit).copy()

    df = infer_candidates(df)
    df = merge_hints(df, load_optional_hints(hints_path))

    df["sequence_sha256"] = df["sequence"].astype(str).map(sha256_text)
    df["structure_lookup_ready"] = (
        df[
            [
                "candidate_uniprot_accession",
                "candidate_afdb_entry_id",
                "candidate_bfvd_model_id",
                "candidate_viro3d_identifier",
            ]
        ]
        .notna()
        .any(axis=1)
    )
    df["built_at"] = now_ts()

    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_tsv, sep="\t", index=False, encoding="utf-8-sig")
    df.to_parquet(out_parquet, index=False)

    summary = {
        "built_at": now_ts(),
        "input_path": str(wide_path),
        "output_tsv": str(out_tsv),
        "output_parquet": str(out_parquet),
        "target_status": cfg["screening"]["target_status"],
        "row_count": int(len(df)),
        "lookup_ready_count": int(df["structure_lookup_ready"].sum()),
        "lookup_ready_fraction": round(float(df["structure_lookup_ready"].mean()), 6) if len(df) else 0.0,
        "hints_used": bool(hints_path.exists()),
    }
    dump_json(summary, summary_json)

    print(f"[OK] target manifest saved: {out_tsv}")
    print(f"[OK] target manifest saved: {out_parquet}")
    print(summary)


if __name__ == "__main__":
    main()
