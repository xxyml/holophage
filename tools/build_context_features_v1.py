from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_TABLE = REPO_ROOT / "data_processed" / "training_labels_wide_with_split.csv"
UPSTREAM_CONTEXT = REPO_ROOT / "dataset_pipeline_portable" / "data" / "1genome_protein_context_phrog.txt"
OUTPUT_PARQUET = REPO_ROOT / "data_processed" / "context_features_v1.parquet"
OUTPUT_SUMMARY = REPO_ROOT / "data_processed" / "context_features_v1.summary.json"

WINDOW_SIZE = 2
VECTOR_COLUMNS = [
    "center_len_norm",
    "neighbor_count_norm",
    "has_left_1",
    "has_right_1",
    "has_left_2",
    "has_right_2",
    "left_1_len_norm",
    "right_1_len_norm",
    "left_2_len_norm",
    "right_2_len_norm",
    "left_1_same_strand",
    "right_1_same_strand",
    "left_2_same_strand",
    "right_2_same_strand",
    "left_1_has_phrog",
    "right_1_has_phrog",
    "left_2_has_phrog",
    "right_2_has_phrog",
]


def phrog_known(value: str | float | int | None) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    text = str(value).strip().lower()
    if text == "" or text == "nan" or text == "<no_phrog_mapping>":
        return 0
    return 1


def len_norm(value: int | float | None, denom: float = 1000.0) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return min(float(value) / denom, 1.0)


def neighbor_feature_row(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("gene_index_ctx").reset_index(drop=True)

    out_rows: list[dict[str, object]] = []
    for idx, row in group.iterrows():
        center_strand = str(row["strand"]).strip()
        center_gene_index = int(row["gene_index_ctx"])
        neighbors: list[str] = []
        features: dict[str, float] = {
            "center_len_norm": len_norm(row["protein_length_aa"]),
            "neighbor_count_norm": 0.0,
            "has_left_1": 0.0,
            "has_right_1": 0.0,
            "has_left_2": 0.0,
            "has_right_2": 0.0,
            "left_1_len_norm": 0.0,
            "right_1_len_norm": 0.0,
            "left_2_len_norm": 0.0,
            "right_2_len_norm": 0.0,
            "left_1_same_strand": 0.0,
            "right_1_same_strand": 0.0,
            "left_2_same_strand": 0.0,
            "right_2_same_strand": 0.0,
            "left_1_has_phrog": 0.0,
            "right_1_has_phrog": 0.0,
            "left_2_has_phrog": 0.0,
            "right_2_has_phrog": 0.0,
        }

        for step in (1, 2):
            left_idx = idx - step
            right_idx = idx + step

            if left_idx >= 0:
                left = group.iloc[left_idx]
                neighbors.append(str(left["protein_id"]))
                features[f"has_left_{step}"] = 1.0
                features[f"left_{step}_len_norm"] = len_norm(left["protein_length_aa"])
                features[f"left_{step}_same_strand"] = 1.0 if str(left["strand"]).strip() == center_strand else 0.0
                features[f"left_{step}_has_phrog"] = float(phrog_known(left["phrog_annotation"]))

            if right_idx < len(group):
                right = group.iloc[right_idx]
                neighbors.append(str(right["protein_id"]))
                features[f"has_right_{step}"] = 1.0
                features[f"right_{step}_len_norm"] = len_norm(right["protein_length_aa"])
                features[f"right_{step}_same_strand"] = 1.0 if str(right["strand"]).strip() == center_strand else 0.0
                features[f"right_{step}_has_phrog"] = float(phrog_known(right["phrog_annotation"]))

        features["neighbor_count_norm"] = min(len(neighbors) / float(WINDOW_SIZE * 2), 1.0)

        out_rows.append(
            {
                "protein_id": str(row["protein_id"]),
                "genome_id": str(row["genome_id_main"]),
                "contig_id": str(row["contig_id"]),
                "gene_index": int(row["gene_index_main"]),
                "homology_cluster_id": str(row["homology_cluster_id"]),
                "split": str(row["split"]),
                "window_size": WINDOW_SIZE,
                "neighbor_count": len(neighbors),
                "neighbor_ids": json.dumps(neighbors, ensure_ascii=False),
                **features,
            }
        )

    return pd.DataFrame(out_rows)


def main() -> None:
    main_df = pd.read_csv(
        MAIN_TABLE,
        usecols=["protein_id", "genome_id", "contig_id", "gene_index", "homology_cluster_id", "split"],
        low_memory=False,
    )
    ctx_df = pd.read_csv(
        UPSTREAM_CONTEXT,
        sep="\t",
        usecols=["protein_id", "genome_id", "accession", "gene_index", "strand", "protein_length_aa", "phrog_annotation"],
        low_memory=False,
    )

    merged = main_df.merge(ctx_df, on="protein_id", how="inner", suffixes=("_main", "_ctx"))
    merged["gene_index_main"] = merged["gene_index_main"].astype("int64")
    merged["gene_index_ctx"] = merged["gene_index_ctx"].astype("int64")
    merged["protein_length_aa"] = merged["protein_length_aa"].astype("int64")

    feature_parts = []
    for _, group in merged.groupby(["genome_id_main", "contig_id"], sort=False):
        feature_parts.append(neighbor_feature_row(group))

    feature_df = pd.concat(feature_parts, axis=0, ignore_index=True)
    feature_df["context_dim"] = len(VECTOR_COLUMNS)

    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    feature_df.to_parquet(OUTPUT_PARQUET, index=False)

    summary = {
        "rows": int(len(feature_df)),
        "context_dim": len(VECTOR_COLUMNS),
        "window_size": WINDOW_SIZE,
        "vector_columns": VECTOR_COLUMNS,
        "input_main_table": str(MAIN_TABLE),
        "input_upstream_context": str(UPSTREAM_CONTEXT),
        "output_parquet": str(OUTPUT_PARQUET),
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
