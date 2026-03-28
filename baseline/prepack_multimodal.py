from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import torch

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from baseline.common import (
    REPO_ROOT,
    apply_active_runtime_paths,
    dump_json,
    ensure_dir,
    load_vocab,
    load_yaml,
    print_runtime_paths,
    resolve_path,
    validate_paths_exist,
    validate_runtime_contract,
)
from baseline.multimodal_v2.assets import (
    ContextFeatureStore,
    ShardedEmbeddingMetaIndex,
    fill_embeddings_by_meta,
    infer_shard_embedding_dim,
)
from baseline.multimodal_v2.types import (
    CONTEXT_FEATURE_DIM,
    DEFAULT_STRUCTURE_EMBEDDING_DIM,
    MULTIMODAL_PACK_SCHEMA_VERSION,
)


REQUIRED_COLUMNS = [
    "protein_id",
    "embedding_id",
    "sequence_embedding_key",
    "genome_id",
    "contig_id",
    "gene_index",
    "sequence_length",
    "split",
    "split_strategy",
    "split_version",
    "exact_sequence_rep_id",
    "homology_cluster_id",
    "status",
    "level1_label",
    "level2_label",
    "node_primary",
    "multi_label_flag",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepack multimodal trainable-core assets.")
    parser.add_argument("--config", default="baseline/train_config.multimodal_v2.stage1.yaml")
    parser.add_argument("--join-index", default=None)
    parser.add_argument("--label-table", default=None)
    parser.add_argument("--sequence-embedding-dir", default=None)
    parser.add_argument("--sequence-embedding-db", default=None)
    parser.add_argument("--structure-embedding-dir", default=None)
    parser.add_argument("--context-source", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--dtype", choices=["float32", "float16"], default="float16")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit-train", type=int, default=None)
    parser.add_argument("--limit-val", type=int, default=None)
    parser.add_argument("--limit-test", type=int, default=None)
    return parser.parse_args()


def load_source_frame(
    join_index_csv: Path,
    limits: dict[str, int | None],
    vocab_l1: dict[str, int],
    vocab_l2: dict[str, int],
    vocab_l3: dict[str, int],
) -> pd.DataFrame:
    df = pd.read_csv(join_index_csv, usecols=REQUIRED_COLUMNS, low_memory=False)
    df = df[df["status"] == "trainable_core"].copy()
    df = df[df["split"].isin(["train", "val", "test"])].copy()
    df = df.dropna(subset=["embedding_id", "level1_label", "level2_label", "node_primary"]).copy()

    for col in (
        "protein_id",
        "embedding_id",
        "sequence_embedding_key",
        "exact_sequence_rep_id",
        "homology_cluster_id",
        "level1_label",
        "level2_label",
        "node_primary",
    ):
        df[col] = df[col].astype(str)

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
    return pd.concat(parts, axis=0, ignore_index=True)


def fetch_sequence_meta_map(db_path: Path, embedding_ids: list[str]) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        meta_map: dict[str, dict[str, Any]] = {}
        chunk_size = 900
        for start in range(0, len(embedding_ids), chunk_size):
            chunk = embedding_ids[start : start + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT embedding_id, shard_name, row_index, orig_seq_len, effective_seq_len, truncated_flag
                FROM embeddings
                WHERE embedding_id IN ({placeholders})
                """,
                chunk,
            ).fetchall()
            for emb_id, shard_name, row_index, orig_seq_len, effective_seq_len, truncated_flag in rows:
                meta_map[str(emb_id)] = {
                    "shard_name": str(shard_name),
                    "row_index": int(row_index),
                    "orig_seq_len": None if orig_seq_len is None else int(orig_seq_len),
                    "effective_seq_len": None if effective_seq_len is None else int(effective_seq_len),
                    "truncated_flag": bool(truncated_flag) if truncated_flag is not None else False,
                }
        return meta_map
    finally:
        conn.close()


def build_split_pack(
    split_df: pd.DataFrame,
    sequence_embedding_dir: Path,
    sequence_meta_map: dict[str, dict[str, Any]],
    structure_embedding_dir: Path | None,
    structure_meta_map: dict[str, dict[str, Any]] | None,
    structure_dim: int,
    context_features: dict[str, torch.Tensor],
    dtype: torch.dtype,
) -> dict[str, Any]:
    n = len(split_df)
    seq_dim = infer_shard_embedding_dim(sequence_embedding_dir)
    sequence_embedding = torch.zeros((n, seq_dim), dtype=dtype)
    structure_embedding = torch.zeros((n, int(structure_dim)), dtype=dtype)
    context_tensor = torch.zeros((n, CONTEXT_FEATURE_DIM), dtype=dtype)
    modality_mask = torch.zeros((n, 3), dtype=torch.bool)

    label_l1 = torch.tensor(split_df["label_l1"].values, dtype=torch.long)
    label_l2 = torch.tensor(split_df["label_l2"].values, dtype=torch.long)
    label_l3 = torch.tensor(split_df["label_l3_core"].values, dtype=torch.long)
    seq_len = torch.tensor(split_df["sequence_length"].fillna(0).astype("int64").values, dtype=torch.long)
    protein_ids = split_df["protein_id"].astype(str).tolist()
    embedding_ids = split_df["embedding_id"].astype(str).tolist()
    exact_ids = split_df["exact_sequence_rep_id"].astype(str).tolist()
    homology_cluster_ids = split_df["homology_cluster_id"].astype(str).tolist()
    split_names = split_df["split"].astype(str).tolist()
    split_strategy = split_df["split_strategy"].astype(str).tolist()
    split_version = split_df["split_version"].astype(str).tolist()
    status = split_df["status"].astype(str).tolist()

    sequence_filled = fill_embeddings_by_meta(
        row_ids=exact_ids,
        meta_map=sequence_meta_map,
        embedding_dir=sequence_embedding_dir,
        target_tensor=sequence_embedding,
        dtype=dtype,
    )
    if sequence_filled != n:
        raise RuntimeError(
            f"Missing sequence embeddings in split pack: filled {sequence_filled}/{n}. "
            "Sequence embedding is required for every row."
        )

    structure_filled = 0
    if structure_embedding_dir is not None and structure_meta_map is not None:
        structure_filled = fill_embeddings_by_meta(
            row_ids=exact_ids,
            meta_map=structure_meta_map,
            embedding_dir=structure_embedding_dir,
            target_tensor=structure_embedding,
            dtype=dtype,
        )

    for idx, protein_id in enumerate(protein_ids):
        modality_mask[idx, 0] = True
        if structure_meta_map is not None and exact_ids[idx] in structure_meta_map:
            modality_mask[idx, 1] = True
        feature = context_features.get(protein_id)
        if feature is not None:
            context_tensor[idx] = feature.to(dtype=dtype)
            modality_mask[idx, 2] = True

    return {
        "schema_version": MULTIMODAL_PACK_SCHEMA_VERSION,
        "sequence_embedding": sequence_embedding,
        "structure_embedding": structure_embedding,
        "context_features": context_tensor,
        "modality_mask": modality_mask,
        "label_l1": label_l1,
        "label_l2": label_l2,
        "label_l3_core": label_l3,
        "sequence_length": seq_len,
        "protein_id": protein_ids,
        "embedding_id": embedding_ids,
        "exact_sequence_rep_id": exact_ids,
        "homology_cluster_id": homology_cluster_ids,
        "split": split_names,
        "split_strategy": split_strategy,
        "split_version": split_version,
        "status": status,
        "build_stats": {
            "rows": int(n),
            "sequence_filled": int(sequence_filled),
            "structure_filled": int(structure_filled),
            "context_filled": int(modality_mask[:, 2].sum().item()),
            "sequence_dim": int(seq_dim),
            "structure_dim": int(structure_dim),
            "context_dim": int(CONTEXT_FEATURE_DIM),
        },
    }


def main() -> None:
    args = parse_args()
    config = apply_active_runtime_paths(load_yaml(resolve_path(args.config, REPO_ROOT)))
    multimodal = config.get("multimodal", {}) or {}
    modalities = multimodal.get("modalities", {}) or {}
    assets = multimodal.get("assets", {}) or {}
    use_structure = bool(modalities.get("structure", False))
    use_context = bool(modalities.get("context", False))

    runtime_paths = {
        "label_table_csv": resolve_path(
            args.label_table or config["data"]["label_table_csv"],
            REPO_ROOT,
        ),
        "join_index_csv": resolve_path(
            args.join_index or config["data"]["join_index_csv"],
            REPO_ROOT,
        ),
        "embedding_index_db": resolve_path(
            args.sequence_embedding_db or config["data"]["embedding_index_db"],
            REPO_ROOT,
        ),
        "embedding_dir": resolve_path(
            args.sequence_embedding_dir or config["data"]["embedding_dir"],
            REPO_ROOT,
        ),
    }
    if use_structure:
        structure_dir = args.structure_embedding_dir or assets.get("structure_embedding_dir")
        if not structure_dir:
            raise ValueError("multimodal.structure=true but structure_embedding_dir is not configured.")
        runtime_paths["structure_embedding_dir"] = resolve_path(structure_dir, REPO_ROOT)
    if use_context:
        context_path = args.context_source or assets.get("context_feature_table")
        if not context_path:
            raise ValueError("multimodal.context=true but context_feature_table is not configured.")
        runtime_paths["context_source_path"] = resolve_path(context_path, REPO_ROOT)

    print_runtime_paths(runtime_paths)
    validate_paths_exist(runtime_paths)
    validate_runtime_contract(config, {
        "label_table_csv": runtime_paths["label_table_csv"],
        "join_index_csv": runtime_paths["join_index_csv"],
        "vocab_l1": resolve_path("outputs/label_vocab_l1.json", REPO_ROOT),
        "vocab_l2": resolve_path("outputs/label_vocab_l2.json", REPO_ROOT),
        "vocab_l3_core": resolve_path("outputs/label_vocab_l3_core.json", REPO_ROOT),
        "embedding_dir": runtime_paths["embedding_dir"],
        "embedding_index_db": runtime_paths["embedding_index_db"],
        "prepacked_dir": resolve_path(str(args.output_dir or assets.get("prepacked_dir")), REPO_ROOT),
    })

    vocab_l1 = load_vocab(resolve_path("outputs/label_vocab_l1.json", REPO_ROOT))
    vocab_l2 = load_vocab(resolve_path("outputs/label_vocab_l2.json", REPO_ROOT))
    vocab_l3 = load_vocab(resolve_path("outputs/label_vocab_l3_core.json", REPO_ROOT))
    limits = {"train": args.limit_train, "val": args.limit_val, "test": args.limit_test}
    df = load_source_frame(runtime_paths["join_index_csv"], limits, vocab_l1, vocab_l2, vocab_l3)
    if df.empty:
        raise RuntimeError("No rows remain after trainable_core/vocab filtering.")

    output_dir = ensure_dir(resolve_path(str(args.output_dir or assets.get("prepacked_dir")), REPO_ROOT))
    if any(output_dir.glob("multimodal_*.pt")) and not args.overwrite:
        raise FileExistsError(f"{output_dir} already contains multimodal packs; use --overwrite to replace them.")

    sequence_ids = df["exact_sequence_rep_id"].astype(str).tolist()
    protein_ids = df["protein_id"].astype(str).tolist()
    sequence_meta_map = fetch_sequence_meta_map(runtime_paths["embedding_index_db"], sequence_ids)

    structure_meta_map: dict[str, dict[str, Any]] | None = None
    structure_dim = DEFAULT_STRUCTURE_EMBEDDING_DIM
    if use_structure:
        structure_meta_index = ShardedEmbeddingMetaIndex(runtime_paths["structure_embedding_dir"])
        structure_meta_map = structure_meta_index.build_meta_map(sequence_ids)
        structure_dim = infer_shard_embedding_dim(runtime_paths["structure_embedding_dir"])

    context_map: dict[str, torch.Tensor] = {}
    if use_context:
        context_store = ContextFeatureStore(runtime_paths["context_source_path"])
        context_map = context_store.prefetch(protein_ids)

    print(
        f"[prepack] coverage seq={len(sequence_meta_map)}/{len(df)} "
        f"struct={0 if structure_meta_map is None else len(structure_meta_map)}/{len(df)} "
        f"ctx={len(context_map)}/{len(df)}"
    )

    dtype = torch.float16 if args.dtype == "float16" else torch.float32
    summary: dict[str, Any] = {
        "schema_version": MULTIMODAL_PACK_SCHEMA_VERSION,
        "output_dir": str(output_dir),
        "dtype": str(dtype),
        "target_status": "trainable_core",
        "sequence_embedding_key": "exact_sequence_rep_id",
        "structure_embedding_key": "exact_sequence_rep_id",
        "context_key": "protein_id",
        "feature_dims": {
            "sequence_embedding": int(infer_shard_embedding_dim(runtime_paths["embedding_dir"])),
            "structure_embedding": int(structure_dim),
            "context_features": int(CONTEXT_FEATURE_DIM),
        },
        "modalities": {
            "sequence": True,
            "structure": use_structure,
            "context": use_context,
        },
        "splits": {},
    }

    for split in ("train", "val", "test"):
        split_df = df[df["split"] == split].copy().reset_index(drop=True)
        pack_path = output_dir / f"multimodal_{split}.pt"
        if pack_path.exists() and not args.overwrite:
            raise FileExistsError(f"{pack_path} exists; use --overwrite to replace it.")

        print(f"[prepack] building {split}: rows={len(split_df)}")
        payload = build_split_pack(
            split_df=split_df,
            sequence_embedding_dir=runtime_paths["embedding_dir"],
            sequence_meta_map=sequence_meta_map,
            structure_embedding_dir=runtime_paths.get("structure_embedding_dir"),
            structure_meta_map=structure_meta_map,
            structure_dim=structure_dim,
            context_features=context_map,
            dtype=dtype,
        )
        payload["split_name"] = split
        torch.save(payload, pack_path)
        summary["splits"][split] = {
            "rows": int(len(split_df)),
            "path": str(pack_path),
            "cluster_count": int(split_df["homology_cluster_id"].nunique()),
            "exact_sequence_group_count": int(split_df["exact_sequence_rep_id"].nunique()),
            "sequence_filled": int(payload["build_stats"]["sequence_filled"]),
            "structure_filled": int(payload["build_stats"]["structure_filled"]),
            "context_filled": int(payload["build_stats"]["context_filled"]),
        }
        print(f"[prepack] saved: {pack_path}")

    dump_json(summary, output_dir / "summary.json")
    print(f"[prepack] summary: {output_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
