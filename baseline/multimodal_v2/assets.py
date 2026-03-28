from __future__ import annotations

from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import torch

from .types import CONTEXT_FEATURE_DIM, CONTEXT_FEATURE_NAMES


def infer_shard_embedding_dim(embedding_dir: str | Path) -> int:
    embedding_dir = Path(embedding_dir)
    shard_paths = sorted(embedding_dir.glob("shard_*.pt"))
    if not shard_paths:
        raise FileNotFoundError(f"No shard_*.pt files found in {embedding_dir}")
    shard = torch.load(shard_paths[0], map_location="cpu")
    return int(shard["embeddings"].shape[1])


class ShardedEmbeddingMetaIndex:
    """Lightweight exact-id -> shard metadata index for sharded torch embeddings."""

    def __init__(self, embedding_dir: str | Path) -> None:
        self.embedding_dir = Path(embedding_dir)
        self._shard_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache_size = 2

    def _load_shard(self, shard_name: str) -> dict[str, Any]:
        if shard_name in self._shard_cache:
            shard = self._shard_cache.pop(shard_name)
            self._shard_cache[shard_name] = shard
            return shard
        shard_path = self.embedding_dir / shard_name
        if not shard_path.exists():
            raise FileNotFoundError(f"Missing embedding shard: {shard_path}")
        shard = torch.load(shard_path, map_location="cpu")
        self._shard_cache[shard_name] = shard
        while len(self._shard_cache) > self._cache_size:
            self._shard_cache.popitem(last=False)
        return shard

    def build_meta_map(self, embedding_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        wanted = {str(embedding_id) for embedding_id in embedding_ids}
        meta_map: dict[str, dict[str, Any]] = {}
        if not wanted:
            return meta_map

        for shard_path in sorted(self.embedding_dir.glob("shard_*.pt")):
            shard = self._load_shard(shard_path.name)
            ids = [str(x) for x in shard["ids"]]
            orig_seq_lens = shard.get("orig_seq_lens")
            effective_seq_lens = shard.get("effective_seq_lens")
            truncated_flags = shard.get("truncated_flags")
            for row_index, embedding_id in enumerate(ids):
                if embedding_id not in wanted or embedding_id in meta_map:
                    continue
                meta_map[embedding_id] = {
                    "shard_name": shard_path.name,
                    "row_index": int(row_index),
                    "orig_seq_len": None
                    if orig_seq_lens is None
                    else int(orig_seq_lens[row_index]),
                    "effective_seq_len": None
                    if effective_seq_lens is None
                    else int(effective_seq_lens[row_index]),
                    "truncated_flag": False
                    if truncated_flags is None
                    else bool(truncated_flags[row_index]),
                }
            if len(meta_map) == len(wanted):
                break
        return meta_map


def build_context_feature_vector(row: dict[str, Any] | pd.Series) -> torch.Tensor:
    values = [float(row.get(name, 0.0) or 0.0) for name in CONTEXT_FEATURE_NAMES]
    tensor = torch.tensor(values, dtype=torch.float32)
    if tensor.numel() != CONTEXT_FEATURE_DIM:
        raise ValueError(
            f"Context feature dim mismatch: got {tensor.numel()}, expected {CONTEXT_FEATURE_DIM}."
        )
    return tensor


class ContextFeatureStore:
    """Chunked loader for instance-level context features keyed by protein_id."""

    def __init__(self, source_path: str | Path, chunksize: int = 250_000) -> None:
        self.source_path = Path(source_path)
        self.chunksize = int(chunksize)

    def prefetch(self, protein_ids: Iterable[str]) -> dict[str, torch.Tensor]:
        wanted = {str(pid) for pid in protein_ids}
        if not wanted:
            return {}
        if not self.source_path.exists():
            raise FileNotFoundError(f"Context source not found: {self.source_path}")

        context_map: dict[str, torch.Tensor] = {}
        if self.source_path.suffix.lower() == ".parquet":
            frame = pd.read_parquet(self.source_path)
            frame = frame[frame["protein_id"].astype(str).isin(wanted)].copy()
            for _, row in frame.iterrows():
                protein_id = str(row["protein_id"])
                context_map[protein_id] = build_context_feature_vector(row)
            return context_map
        raise ValueError(
            "ContextFeatureStore currently expects data_processed/context_features_v1.parquet "
            f"with vector columns {list(CONTEXT_FEATURE_NAMES)!r}; got {self.source_path}."
        )


def fill_embeddings_by_meta(
    row_ids: list[str],
    meta_map: dict[str, dict[str, Any]],
    embedding_dir: str | Path,
    target_tensor: torch.Tensor,
    dtype: torch.dtype,
) -> int:
    embedding_dir = Path(embedding_dir)
    shard_groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for packed_index, embedding_id in enumerate(row_ids):
        meta = meta_map.get(str(embedding_id))
        if meta is None:
            continue
        shard_groups[str(meta["shard_name"])].append((packed_index, int(meta["row_index"])))

    filled = 0
    for shard_name, pairs in shard_groups.items():
        shard_path = embedding_dir / shard_name
        if not shard_path.exists():
            raise FileNotFoundError(f"Missing shard: {shard_path}")
        shard = torch.load(shard_path, map_location="cpu")
        source_indices = torch.tensor([source_idx for _, source_idx in pairs], dtype=torch.long)
        target_indices = torch.tensor([target_idx for target_idx, _ in pairs], dtype=torch.long)
        target_tensor[target_indices] = shard["embeddings"][source_indices].to(dtype=dtype)
        filled += len(pairs)
    return filled
