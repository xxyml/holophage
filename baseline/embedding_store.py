from __future__ import annotations

import sqlite3
from collections import OrderedDict
from pathlib import Path
from typing import Any

import torch


class EmbeddingStore:
    """SQLite-backed lookup for ProstT5 shard embeddings."""

    def __init__(self, db_path: str | Path, embedding_dir: str | Path, cache_size: int = 2) -> None:
        self.db_path = Path(db_path)
        self.embedding_dir = Path(embedding_dir)
        self.cache_size = max(1, cache_size)
        self._conn: sqlite3.Connection | None = None
        self._shard_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            uri = f"file:{self.db_path.as_posix()}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._shard_cache.clear()

    def __del__(self) -> None:
        self.close()

    def has(self, embedding_id: str) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT 1 FROM embeddings WHERE embedding_id = ? LIMIT 1",
            (embedding_id,),
        ).fetchone()
        return row is not None

    def get_metadata(self, embedding_id: str) -> dict[str, Any]:
        conn = self._connect()
        row = conn.execute(
            """
            SELECT shard_name, row_index, orig_seq_len, effective_seq_len, truncated_flag
            FROM embeddings
            WHERE embedding_id = ?
            """,
            (embedding_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Embedding id not found: {embedding_id}")
        return {
            "shard_name": row[0],
            "row_index": int(row[1]),
            "orig_seq_len": None if row[2] is None else int(row[2]),
            "effective_seq_len": None if row[3] is None else int(row[3]),
            "truncated_flag": bool(row[4]) if row[4] is not None else False,
        }

    def get_embedding(self, embedding_id: str) -> torch.Tensor:
        meta = self.get_metadata(embedding_id)
        shard = self._load_shard(meta["shard_name"])
        return shard["embeddings"][meta["row_index"]].float()

    def _load_shard(self, shard_name: str) -> dict[str, Any]:
        if shard_name in self._shard_cache:
            shard = self._shard_cache.pop(shard_name)
            self._shard_cache[shard_name] = shard
            return shard

        shard_path = self.embedding_dir / shard_name
        if not shard_path.exists():
            raise FileNotFoundError(f"Embedding shard missing: {shard_path}")
        shard = torch.load(shard_path, map_location="cpu")
        self._shard_cache[shard_name] = shard
        while len(self._shard_cache) > self.cache_size:
            self._shard_cache.popitem(last=False)
        return shard
