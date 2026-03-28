from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import torch

from baseline.common import (
    REPO_ROOT,
    apply_active_runtime_paths,
    dump_json,
    ensure_dir,
    load_vocab,
    load_yaml,
    print_runtime_paths,
    resolve_path,
    resolve_runtime_paths,
    validate_paths_exist,
    validate_runtime_contract,
)


REQUIRED_COLUMNS = [
    "protein_id",
    "embedding_id",
    "sequence_length",
    "split",
    "split_strategy",
    "split_version",
    "status",
    "level1_label",
    "level2_label",
    "node_primary",
    "homology_cluster_id",
    "exact_sequence_rep_id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepack trainable-core embeddings for fast training.")
    parser.add_argument("--config", default="baseline/train_config.full_stage2.yaml")
    parser.add_argument("--output-dir", default="baseline/artifacts/prepacked_core_exact")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dtype", choices=["float32", "float16"], default="float32")
    parser.add_argument("--limit-train", type=int, default=None)
    parser.add_argument("--limit-val", type=int, default=None)
    parser.add_argument("--limit-test", type=int, default=None)
    return parser.parse_args()


def fetch_meta_map(db_path: Path, embedding_ids: list[str]) -> dict[str, tuple[str, int]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Embedding index DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        meta_map: dict[str, tuple[str, int]] = {}
        chunk_size = 900
        for start in range(0, len(embedding_ids), chunk_size):
            chunk = embedding_ids[start : start + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT embedding_id, shard_name, row_index
                FROM embeddings
                WHERE embedding_id IN ({placeholders})
                """,
                chunk,
            ).fetchall()
            for emb_id, shard_name, row_index in rows:
                meta_map[str(emb_id)] = (str(shard_name), int(row_index))
        return meta_map
    finally:
        conn.close()


def load_filtered_df(config: dict[str, Any], limits: dict[str, int | None]) -> tuple[pd.DataFrame, dict[str, int], dict[str, int], dict[str, int]]:
    join_index_csv = resolve_path(config["data"]["join_index_csv"], REPO_ROOT)
    df = pd.read_csv(join_index_csv, usecols=REQUIRED_COLUMNS, low_memory=False)
    df = df[df["status"] == "trainable_core"].copy()
    df = df[df["split"].isin(["train", "val", "test"])].copy()
    df = df.dropna(subset=["embedding_id", "level1_label", "level2_label", "node_primary"]).copy()

    df["level1_label"] = df["level1_label"].astype(str)
    df["level2_label"] = df["level2_label"].astype(str)
    df["node_primary"] = df["node_primary"].astype(str)
    df["embedding_id"] = df["embedding_id"].astype(str)
    df["protein_id"] = df["protein_id"].astype(str)

    vocab_l1 = load_vocab(resolve_path(config["data"]["vocab_l1"], REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path(config["data"]["vocab_l2"], REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path(config["data"]["vocab_l3_core"], REPO_ROOT))

    df = df[
        df["level1_label"].isin(vocab_l1)
        & df["level2_label"].isin(vocab_l2)
        & df["node_primary"].isin(vocab_l3)
    ].copy()

    df["label_l1"] = df["level1_label"].map(vocab_l1).astype("int64")
    df["label_l2"] = df["level2_label"].map(vocab_l2).astype("int64")
    df["label_l3_core"] = df["node_primary"].map(vocab_l3).astype("int64")

    parts: list[pd.DataFrame] = []
    for split in ("train", "val", "test"):
        split_df = df[df["split"] == split].copy()
        limit = limits.get(split)
        if limit is not None:
            split_df = split_df.head(int(limit)).copy()
        parts.append(split_df)

    merged = pd.concat(parts, axis=0, ignore_index=True)
    return merged, vocab_l1, vocab_l2, vocab_l3


def build_split_pack(
    split_df: pd.DataFrame,
    embed_dir: Path,
    dtype: torch.dtype,
) -> dict[str, Any]:
    n = len(split_df)
    if n == 0:
        return {
            "embedding": torch.empty((0, 1024), dtype=dtype),
            "label_l1": torch.empty((0,), dtype=torch.long),
            "label_l2": torch.empty((0,), dtype=torch.long),
            "label_l3_core": torch.empty((0,), dtype=torch.long),
            "sequence_length": torch.empty((0,), dtype=torch.long),
            "protein_id": [],
            "embedding_id": [],
            "split_strategy": [],
            "split_version": [],
            "homology_cluster_id": [],
            "exact_sequence_rep_id": [],
        }

    embeddings = torch.empty((n, 1024), dtype=dtype)
    label_l1 = torch.tensor(split_df["label_l1"].values, dtype=torch.long)
    label_l2 = torch.tensor(split_df["label_l2"].values, dtype=torch.long)
    label_l3 = torch.tensor(split_df["label_l3_core"].values, dtype=torch.long)
    seq_len = torch.tensor(split_df["sequence_length"].fillna(0).astype("int64").values, dtype=torch.long)
    protein_ids = split_df["protein_id"].tolist()
    embedding_ids = split_df["embedding_id"].tolist()
    split_strategy = split_df["split_strategy"].astype(str).tolist()
    split_version = split_df["split_version"].astype(str).tolist()
    homology_cluster_ids = split_df["homology_cluster_id"].astype(str).tolist()
    exact_sequence_rep_ids = split_df["exact_sequence_rep_id"].astype(str).tolist()

    by_shard: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for packed_idx, row in split_df.iterrows():
        local_idx = int(row["packed_index"])
        by_shard[str(row["shard_name"])].append((local_idx, int(row["row_index"])))

    for shard_name, pairs in by_shard.items():
        shard_path = embed_dir / shard_name
        if not shard_path.exists():
            raise FileNotFoundError(f"Missing shard: {shard_path}")
        shard = torch.load(shard_path, map_location="cpu")
        shard_embeddings = shard["embeddings"]

        target_indices = torch.tensor([p[0] for p in pairs], dtype=torch.long)
        source_indices = torch.tensor([p[1] for p in pairs], dtype=torch.long)
        chunk = shard_embeddings[source_indices].to(dtype=dtype)
        embeddings[target_indices] = chunk

    return {
        "embedding": embeddings,
        "label_l1": label_l1,
        "label_l2": label_l2,
        "label_l3_core": label_l3,
        "sequence_length": seq_len,
        "protein_id": protein_ids,
        "embedding_id": embedding_ids,
        "split_strategy": split_strategy,
        "split_version": split_version,
        "homology_cluster_id": homology_cluster_ids,
        "exact_sequence_rep_id": exact_sequence_rep_ids,
    }


def main() -> None:
    args = parse_args()
    config = apply_active_runtime_paths(load_yaml(resolve_path(args.config, REPO_ROOT)))
    runtime_paths = resolve_runtime_paths(config)
    print_runtime_paths(runtime_paths)
    validate_paths_exist(
        {
            "label_table_csv": runtime_paths["label_table_csv"],
            "join_index_csv": runtime_paths["join_index_csv"],
            "vocab_l1": runtime_paths["vocab_l1"],
            "vocab_l2": runtime_paths["vocab_l2"],
            "vocab_l3_core": runtime_paths["vocab_l3_core"],
            "embedding_dir": runtime_paths["embedding_dir"],
            "embedding_index_db": runtime_paths["embedding_index_db"],
        }
    )
    validate_runtime_contract(config, runtime_paths)
    output_dir = ensure_dir(resolve_path(args.output_dir, REPO_ROOT))
    embed_dir = resolve_path(config["data"]["embedding_dir"], REPO_ROOT)
    embedding_db_path = resolve_path(config["data"]["embedding_index_db"], REPO_ROOT)

    limits = {"train": args.limit_train, "val": args.limit_val, "test": args.limit_test}
    df, vocab_l1, vocab_l2, vocab_l3 = load_filtered_df(config, limits=limits)
    if df.empty:
        raise RuntimeError("No rows remain after trainable_core/vocab filtering.")

    ids = df["exact_sequence_rep_id"].astype(str).tolist()
    meta_map = fetch_meta_map(embedding_db_path, ids)
    df["meta"] = df["exact_sequence_rep_id"].map(meta_map)
    df = df.dropna(subset=["meta"]).copy()
    df["shard_name"] = df["meta"].map(lambda x: x[0])
    df["row_index"] = df["meta"].map(lambda x: x[1])
    df = df.drop(columns=["meta"])

    dtype = torch.float16 if args.dtype == "float16" else torch.float32
    summary: dict[str, Any] = {
        "output_dir": str(output_dir),
        "dtype": str(dtype),
        "schema_version": "core_prepacked_v2_sampler_ready",
        "sampler_ready": True,
        "sequence_embedding_lookup_key": "exact_sequence_rep_id",
        "total_rows": int(len(df)),
        "splits": {},
        "vocabs": {
            "l1": len(vocab_l1),
            "l2": len(vocab_l2),
            "l3_core": len(vocab_l3),
        },
    }

    for split in ("train", "val", "test"):
        split_df = df[df["split"] == split].copy().reset_index(drop=True)
        split_df["packed_index"] = split_df.index.astype("int64")
        pack_path = output_dir / f"core_{split}.pt"
        if pack_path.exists() and not args.overwrite:
            raise FileExistsError(f"{pack_path} exists, use --overwrite to replace it.")

        print(f"[prepack] building {split}: rows={len(split_df)}")
        payload = build_split_pack(split_df, embed_dir=embed_dir, dtype=dtype)
        payload["split"] = split
        torch.save(payload, pack_path)

        summary["splits"][split] = {
            "rows": int(len(split_df)),
            "path": str(pack_path),
            "cluster_count": int(split_df["homology_cluster_id"].nunique()),
            "exact_sequence_group_count": int(split_df["exact_sequence_rep_id"].nunique()),
        }
        print(f"[prepack] saved: {pack_path}")

    dump_json(summary, output_dir / "summary.json")
    print(f"[prepack] summary: {output_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
