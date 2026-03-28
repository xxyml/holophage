from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import torch

from baseline.common import (
    REPO_ROOT,
    apply_active_runtime_paths,
    ensure_dir,
    load_yaml,
    print_runtime_paths,
    resolve_path,
    resolve_runtime_paths,
    validate_paths_exist,
    validate_runtime_contract,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SQLite index for exact sequence embedding shards.")
    parser.add_argument("--config", default="baseline/train_config.full_stage2.yaml", help="Path to baseline config yaml.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing index database.")
    return parser.parse_args()


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            embedding_id TEXT PRIMARY KEY,
            shard_name TEXT NOT NULL,
            row_index INTEGER NOT NULL,
            orig_seq_len INTEGER,
            effective_seq_len INTEGER,
            truncated_flag INTEGER DEFAULT 0
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_shard ON embeddings (shard_name)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    return conn


def scalar_at(values, idx: int) -> int | None:
    if values is None:
        return None
    item = values[idx]
    if item is None:
        return None
    if hasattr(item, "item"):
        return int(item.item())
    return int(item)


def build_index(embed_dir: Path, db_path: Path, overwrite: bool = False) -> None:
    if overwrite and db_path.exists():
        db_path.unlink()

    shard_paths = sorted(embed_dir.glob("*.pt"))
    if not shard_paths:
        raise FileNotFoundError(f"No embedding shards found in {embed_dir}")

    conn = init_db(db_path)
    total_rows = 0
    try:
        conn.execute("DELETE FROM embeddings")
        conn.execute("DELETE FROM metadata")
        conn.commit()

        for shard_idx, shard_path in enumerate(shard_paths, start=1):
            print(f"[index] loading {shard_idx}/{len(shard_paths)}: {shard_path.name}")
            shard = torch.load(shard_path, map_location="cpu")
            ids = shard["ids"]
            orig = shard.get("orig_seq_lens")
            effective = shard.get("effective_seq_lens")
            truncated = shard.get("truncated_flags")

            rows = [
                (
                    str(ids[row_idx]),
                    shard_path.name,
                    row_idx,
                    scalar_at(orig, row_idx),
                    scalar_at(effective, row_idx),
                    scalar_at(truncated, row_idx) if truncated is not None else 0,
                )
                for row_idx in range(len(ids))
            ]
            conn.executemany(
                """
                INSERT INTO embeddings (
                    embedding_id, shard_name, row_index, orig_seq_len, effective_seq_len, truncated_flag
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            total_rows += len(rows)

        conn.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            [
                ("repo_root", str(REPO_ROOT)),
                ("embed_dir", str(embed_dir)),
                ("sequence_embedding_lookup_key", "exact_sequence_rep_id"),
                ("shard_count", str(len(shard_paths))),
                ("row_count", str(total_rows)),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    print(f"[index] complete: {db_path}")
    print(f"[index] shards indexed: {len(shard_paths)}")
    print(f"[index] rows indexed: {total_rows}")
    if len(shard_paths) == 1:
        print(
            "[index] warning: only 1 shard found. Confirm "
            "D:\\data\\ai4s\\holophage\\embedding_pipeline\\outputs\\embed_exact "
            "contains the full exact shard set, then rebuild the exact index."
        )


def main() -> None:
    args = parse_args()
    config_path = resolve_path(args.config, REPO_ROOT)
    config = apply_active_runtime_paths(load_yaml(config_path))
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
        }
    )
    validate_runtime_contract(config, runtime_paths)
    embed_dir = resolve_path(config["data"]["embedding_dir"], REPO_ROOT)
    db_path = resolve_path(config["data"]["embedding_index_db"], REPO_ROOT)
    ensure_dir(db_path.parent)
    build_index(embed_dir=embed_dir, db_path=db_path, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
