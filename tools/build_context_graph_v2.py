from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baseline.multimodal_v2.types import (
    CONTEXT_GRAPH_CENTER_INDEX,
    CONTEXT_GRAPH_MAX_NODES,
    CONTEXT_GRAPH_NODE_FEATURE_NAMES,
    CONTEXT_GRAPH_VERSION_V2A,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_TABLE = REPO_ROOT / "data_processed" / "training_labels_wide_with_split.csv"
UPSTREAM_CONTEXT = REPO_ROOT / "dataset_pipeline_portable" / "data" / "1genome_protein_context_phrog.txt"
OUTPUT_DIR = REPO_ROOT / "data_processed"
WINDOW_SIZES = (1, 2, 4)
OFFSETS = tuple(range(-4, 5))


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


def strand_flags(value: object) -> tuple[float, float]:
    text = str(value).strip()
    if text in {"+", "1", "forward", "f"}:
        return 1.0, 0.0
    if text in {"-", "-1", "reverse", "r"}:
        return 0.0, 1.0
    return 0.0, 0.0


def build_node_feature(row: pd.Series, offset: int, is_center: bool) -> list[float]:
    strand_forward, strand_reverse = strand_flags(row.get("strand"))
    features = [
        len_norm(row.get("protein_length_aa")),
        strand_forward,
        strand_reverse,
        float(phrog_known(row.get("phrog_annotation"))),
        1.0 if is_center else 0.0,
    ]
    for slot in OFFSETS:
        features.append(1.0 if slot == offset else 0.0)
    return features


def build_empty_graph() -> tuple[list[list[float]], list[list[float]], list[bool]]:
    node_features = [[0.0] * len(CONTEXT_GRAPH_NODE_FEATURE_NAMES) for _ in range(CONTEXT_GRAPH_MAX_NODES)]
    adjacency = [[0.0] * CONTEXT_GRAPH_MAX_NODES for _ in range(CONTEXT_GRAPH_MAX_NODES)]
    node_mask = [False] * CONTEXT_GRAPH_MAX_NODES
    return node_features, adjacency, node_mask


def add_undirected_edge(adjacency: list[list[float]], i: int, j: int) -> None:
    adjacency[i][j] = 1.0
    adjacency[j][i] = 1.0


def build_graph_row(group: pd.DataFrame, center_idx: int, window_size: int) -> dict[str, object]:
    center_row = group.iloc[center_idx]
    node_features, adjacency, node_mask = build_empty_graph()
    valid_indices: dict[int, int] = {}

    for slot_idx, offset in enumerate(OFFSETS):
        if abs(offset) > int(window_size):
            continue
        neighbor_idx = center_idx + offset
        if neighbor_idx < 0 or neighbor_idx >= len(group):
            continue
        row = group.iloc[neighbor_idx]
        node_features[slot_idx] = build_node_feature(row, offset=offset, is_center=(offset == 0))
        node_mask[slot_idx] = True
        valid_indices[offset] = slot_idx

    for left, right in zip(OFFSETS[:-1], OFFSETS[1:]):
        left_slot = valid_indices.get(left)
        right_slot = valid_indices.get(right)
        if left_slot is not None and right_slot is not None:
            add_undirected_edge(adjacency, left_slot, right_slot)

    center_slot = valid_indices.get(0)
    if center_slot is not None:
        for offset, slot_idx in valid_indices.items():
            if offset == 0:
                continue
            add_undirected_edge(adjacency, center_slot, slot_idx)

    return {
        "protein_id": str(center_row["protein_id"]),
        "genome_id": str(center_row["genome_id_main"]),
        "contig_id": str(center_row["contig_id"]),
        "gene_index": int(center_row["gene_index_main"]),
        "homology_cluster_id": str(center_row["homology_cluster_id"]),
        "split": str(center_row["split"]),
        "split_strategy": str(center_row["split_strategy"]),
        "split_version": str(center_row["split_version"]),
        "window_size": int(window_size),
        "center_index": int(CONTEXT_GRAPH_CENTER_INDEX),
        "num_valid_nodes": int(sum(node_mask)),
        "graph_version": CONTEXT_GRAPH_VERSION_V2A,
        "node_features_flat": json.dumps([x for row in node_features for x in row], ensure_ascii=False),
        "adjacency_flat": json.dumps([x for row in adjacency for x in row], ensure_ascii=False),
        "node_mask_flat": json.dumps(node_mask, ensure_ascii=False),
    }


def build_window_frame(merged: pd.DataFrame, window_size: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, group in merged.groupby(["genome_id_main", "contig_id"], sort=False):
        group = group.sort_values("gene_index_ctx").reset_index(drop=True)
        for center_idx in range(len(group)):
            rows.append(build_graph_row(group, center_idx=center_idx, window_size=window_size))
    return pd.DataFrame(rows)


def main() -> None:
    main_df = pd.read_csv(
        MAIN_TABLE,
        usecols=[
            "protein_id",
            "genome_id",
            "contig_id",
            "gene_index",
            "homology_cluster_id",
            "split",
            "split_strategy",
            "split_version",
        ],
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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for window_size in WINDOW_SIZES:
        feature_df = build_window_frame(merged, window_size=window_size)
        out_path = OUTPUT_DIR / f"context_graph_features_v2a_window{window_size}.parquet"
        summary_path = OUTPUT_DIR / f"context_graph_features_v2a_window{window_size}.summary.json"
        feature_df.to_parquet(out_path, index=False)
        summary = {
            "rows": int(len(feature_df)),
            "window_size": int(window_size),
            "graph_version": CONTEXT_GRAPH_VERSION_V2A,
            "max_nodes": int(CONTEXT_GRAPH_MAX_NODES),
            "center_index": int(CONTEXT_GRAPH_CENTER_INDEX),
            "node_feature_dim": int(len(CONTEXT_GRAPH_NODE_FEATURE_NAMES)),
            "node_feature_names": list(CONTEXT_GRAPH_NODE_FEATURE_NAMES),
            "input_main_table": str(MAIN_TABLE),
            "input_upstream_context": str(UPSTREAM_CONTEXT),
            "output_parquet": str(out_path),
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
