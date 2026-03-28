from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from torch.utils.data import Dataset

from baseline.common import load_vocab
from baseline.embedding_store import EmbeddingStore


@dataclass
class LabelVocabs:
    l1: dict[str, int]
    l2: dict[str, int]
    l3: dict[str, int]


class BaselineCoreDataset(Dataset):
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

    def __init__(
        self,
        join_index_csv: str | Path,
        embedding_db_path: str | Path,
        embedding_dir: str | Path,
        vocab_l1_path: str | Path,
        vocab_l2_path: str | Path,
        vocab_l3_path: str | Path,
        split: str,
        limit: int | None = None,
    ) -> None:
        self.join_index_csv = Path(join_index_csv)
        self.embedding_db_path = Path(embedding_db_path)
        self.embedding_dir = Path(embedding_dir)
        self.split = split
        self.vocabs = LabelVocabs(
            l1=load_vocab(vocab_l1_path),
            l2=load_vocab(vocab_l2_path),
            l3=load_vocab(vocab_l3_path),
        )
        self._embedding_store: EmbeddingStore | None = None

        df = pd.read_csv(self.join_index_csv, usecols=self.REQUIRED_COLUMNS, low_memory=False)
        df = df[df["status"] == "trainable_core"].copy()
        df = df[df["split"] == split].copy()
        df = df.dropna(subset=["embedding_id", "level1_label", "level2_label", "node_primary"])

        df["level1_label"] = df["level1_label"].astype(str)
        df["level2_label"] = df["level2_label"].astype(str)
        df["node_primary"] = df["node_primary"].astype(str)
        df["homology_cluster_id"] = df["homology_cluster_id"].astype(str)
        df["exact_sequence_rep_id"] = df["exact_sequence_rep_id"].astype(str)

        df = df[
            df["level1_label"].isin(self.vocabs.l1)
            & df["level2_label"].isin(self.vocabs.l2)
            & df["node_primary"].isin(self.vocabs.l3)
        ].copy()

        df["label_l1"] = df["level1_label"].map(self.vocabs.l1)
        df["label_l2"] = df["level2_label"].map(self.vocabs.l2)
        df["label_l3_core"] = df["node_primary"].map(self.vocabs.l3)
        df = self._filter_to_available_embeddings(df)

        if limit is not None:
            df = df.head(limit).copy()

        self.df = df.reset_index(drop=True)

    def _filter_to_available_embeddings(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.embedding_db_path.exists():
            return df
        conn = sqlite3.connect(self.embedding_db_path)
        try:
            available = set()
            ids = df["exact_sequence_rep_id"].astype(str).tolist()
            chunk_size = 900
            for start in range(0, len(ids), chunk_size):
                chunk = ids[start : start + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT embedding_id FROM embeddings WHERE embedding_id IN ({placeholders})",
                    chunk,
                ).fetchall()
                available.update(row[0] for row in rows)
        finally:
            conn.close()
        return df[df["exact_sequence_rep_id"].astype(str).isin(available)].copy()

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.df.iloc[index]
        embedding = self.embedding_store.get_embedding(str(row["exact_sequence_rep_id"]))
        return {
            "protein_id": str(row["protein_id"]),
            "embedding_id": str(row["embedding_id"]),
            "embedding": embedding,
            "label_l1": torch.tensor(int(row["label_l1"]), dtype=torch.long),
            "label_l2": torch.tensor(int(row["label_l2"]), dtype=torch.long),
            "label_l3_core": torch.tensor(int(row["label_l3_core"]), dtype=torch.long),
            "sequence_length": torch.tensor(int(row["sequence_length"]), dtype=torch.long),
            "split": str(row["split"]),
            "split_strategy": str(row["split_strategy"]),
            "split_version": str(row["split_version"]),
            "homology_cluster_id": str(row["homology_cluster_id"]),
            "exact_sequence_rep_id": str(row["exact_sequence_rep_id"]),
        }

    @property
    def embedding_store(self) -> EmbeddingStore:
        if self._embedding_store is None:
            self._embedding_store = EmbeddingStore(
                db_path=self.embedding_db_path,
                embedding_dir=self.embedding_dir,
            )
        return self._embedding_store

    def class_weights(self, field: str, num_classes: int) -> torch.Tensor:
        counts = self.df[field].value_counts().to_dict()
        total = float(sum(counts.values()))
        weights = []
        for class_idx in range(num_classes):
            class_count = float(counts.get(class_idx, 0.0))
            if class_count <= 0:
                weights.append(0.0)
            else:
                weights.append(total / (num_classes * class_count))
        return torch.tensor(weights, dtype=torch.float)

    def hierarchy_maps(self) -> tuple[torch.Tensor, torch.Tensor]:
        l3_to_l2 = torch.full((len(self.vocabs.l3),), -1, dtype=torch.long)
        l2_to_l1 = torch.full((len(self.vocabs.l2),), -1, dtype=torch.long)

        for _, row in self.df[["label_l3_core", "label_l2"]].drop_duplicates().iterrows():
            child = int(row["label_l3_core"])
            parent = int(row["label_l2"])
            if l3_to_l2[child] not in (-1, parent):
                raise ValueError(f"Conflicting L3->L2 mapping for class {child}")
            l3_to_l2[child] = parent

        for _, row in self.df[["label_l2", "label_l1"]].drop_duplicates().iterrows():
            child = int(row["label_l2"])
            parent = int(row["label_l1"])
            if l2_to_l1[child] not in (-1, parent):
                raise ValueError(f"Conflicting L2->L1 mapping for class {child}")
            l2_to_l1[child] = parent

        return l3_to_l2, l2_to_l1

    def sampler_frame(self) -> pd.DataFrame:
        frame = self.df[["homology_cluster_id", "exact_sequence_rep_id", "label_l3_core"]].copy()
        frame.insert(0, "row_index", frame.index.astype("int64"))
        return frame
