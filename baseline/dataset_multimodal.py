from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from torch.utils.data import Dataset

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from baseline.multimodal_v2.types import (
    CONTEXT_GRAPH_CENTER_INDEX,
    CONTEXT_GRAPH_MAX_NODES,
    CONTEXT_GRAPH_NODE_FEATURE_DIM,
    CONTEXT_MODE_HANDCRAFTED,
    CONTEXT_FEATURE_DIM,
    DEFAULT_SEQUENCE_EMBEDDING_DIM,
    DEFAULT_STRUCTURE_EMBEDDING_DIM,
    MODALITY_NAMES,
    MULTIMODAL_PACK_SCHEMA_VERSION,
    MultimodalBatch,
    build_ids,
    build_labels,
)


class MultimodalCoreDataset(Dataset):
    REQUIRED_KEYS = {
        "sequence_embedding",
        "structure_embedding",
        "context_features",
        "modality_mask",
        "label_l1",
        "label_l2",
        "label_l3_core",
        "protein_id",
        "embedding_id",
        "exact_sequence_rep_id",
        "homology_cluster_id",
        "split",
        "split_strategy",
        "split_version",
        "status",
        "sequence_length",
    }

    def __init__(self, pack_path: str | Path, limit: int | None = None) -> None:
        self.pack_path = Path(pack_path)
        if not self.pack_path.exists():
            raise FileNotFoundError(f"Multimodal pack not found: {self.pack_path}")

        payload = torch.load(self.pack_path, map_location="cpu")
        missing = self.REQUIRED_KEYS - set(payload.keys())
        if missing:
            raise KeyError(
                f"Missing keys in multimodal pack: {sorted(missing)}. "
                "Rebuild the pack with `python -m baseline.prepack_multimodal --overwrite`."
            )

        self.schema_version = str(payload.get("schema_version", MULTIMODAL_PACK_SCHEMA_VERSION))
        self.context_mode = str(payload.get("context_mode", CONTEXT_MODE_HANDCRAFTED))
        self.context_graph_version = str(payload.get("context_graph_version", ""))
        self.sequence_embedding: torch.Tensor = payload["sequence_embedding"].float().contiguous()
        self.structure_embedding: torch.Tensor = payload["structure_embedding"].float().contiguous()
        self.context_features: torch.Tensor = payload["context_features"].float().contiguous()
        self.context_node_features: torch.Tensor = payload.get(
            "context_node_features",
            torch.zeros((self.sequence_embedding.shape[0], CONTEXT_GRAPH_MAX_NODES, CONTEXT_GRAPH_NODE_FEATURE_DIM), dtype=torch.float32),
        ).float().contiguous()
        self.context_adjacency: torch.Tensor = payload.get(
            "context_adjacency",
            torch.zeros((self.sequence_embedding.shape[0], CONTEXT_GRAPH_MAX_NODES, CONTEXT_GRAPH_MAX_NODES), dtype=torch.float32),
        ).float().contiguous()
        self.context_node_mask: torch.Tensor = payload.get(
            "context_node_mask",
            torch.zeros((self.sequence_embedding.shape[0], CONTEXT_GRAPH_MAX_NODES), dtype=torch.bool),
        ).bool().contiguous()
        self.context_center_index: torch.Tensor = payload.get(
            "context_center_index",
            torch.full((self.sequence_embedding.shape[0],), CONTEXT_GRAPH_CENTER_INDEX, dtype=torch.long),
        ).long().contiguous()
        self.modality_mask: torch.Tensor = payload["modality_mask"].bool().contiguous()
        self.label_l1: torch.Tensor = payload["label_l1"].long().contiguous()
        self.label_l2: torch.Tensor = payload["label_l2"].long().contiguous()
        self.label_l3_core: torch.Tensor = payload["label_l3_core"].long().contiguous()
        self.sequence_length: torch.Tensor = payload["sequence_length"].long().contiguous()

        self.protein_id = [str(x) for x in payload["protein_id"]]
        self.embedding_id = [str(x) for x in payload["embedding_id"]]
        self.exact_sequence_rep_id = [str(x) for x in payload["exact_sequence_rep_id"]]
        self.homology_cluster_id = [str(x) for x in payload["homology_cluster_id"]]
        self.split = [str(x) for x in payload["split"]]
        self.split_strategy = [str(x) for x in payload["split_strategy"]]
        self.split_version = [str(x) for x in payload["split_version"]]
        self.status = [str(x) for x in payload["status"]]

        expected = self.sequence_embedding.shape[0]
        if not (
            self.structure_embedding.shape[0]
            == self.context_features.shape[0]
            == self.context_node_features.shape[0]
            == self.context_adjacency.shape[0]
            == self.context_node_mask.shape[0]
            == len(self.context_center_index)
            == self.modality_mask.shape[0]
            == len(self.label_l1)
            == len(self.label_l2)
            == len(self.label_l3_core)
            == len(self.sequence_length)
            == len(self.protein_id)
            == len(self.embedding_id)
            == len(self.exact_sequence_rep_id)
            == len(self.homology_cluster_id)
            == len(self.split)
            == len(self.split_strategy)
            == len(self.split_version)
            == len(self.status)
            == expected
        ):
            raise ValueError(f"Multimodal pack length mismatch in {self.pack_path}")

        if self.sequence_embedding.shape[1] != DEFAULT_SEQUENCE_EMBEDDING_DIM:
            raise ValueError(
                f"Expected sequence dim {DEFAULT_SEQUENCE_EMBEDDING_DIM}, got {self.sequence_embedding.shape[1]}"
            )
        if self.structure_embedding.shape[1] != DEFAULT_STRUCTURE_EMBEDDING_DIM:
            raise ValueError(
                f"Expected structure dim {DEFAULT_STRUCTURE_EMBEDDING_DIM}, got {self.structure_embedding.shape[1]}"
            )
        if self.context_features.shape[1] != CONTEXT_FEATURE_DIM:
            raise ValueError(f"Expected context dim {CONTEXT_FEATURE_DIM}, got {self.context_features.shape[1]}")
        if self.context_node_features.shape[1:] != (CONTEXT_GRAPH_MAX_NODES, CONTEXT_GRAPH_NODE_FEATURE_DIM):
            raise ValueError(
                f"Expected context graph node features {(CONTEXT_GRAPH_MAX_NODES, CONTEXT_GRAPH_NODE_FEATURE_DIM)}, "
                f"got {tuple(self.context_node_features.shape[1:])}"
            )
        if self.context_adjacency.shape[1:] != (CONTEXT_GRAPH_MAX_NODES, CONTEXT_GRAPH_MAX_NODES):
            raise ValueError(
                f"Expected context adjacency {(CONTEXT_GRAPH_MAX_NODES, CONTEXT_GRAPH_MAX_NODES)}, "
                f"got {tuple(self.context_adjacency.shape[1:])}"
            )
        if self.context_node_mask.shape[1] != CONTEXT_GRAPH_MAX_NODES:
            raise ValueError(
                f"Expected context node mask width {CONTEXT_GRAPH_MAX_NODES}, got {self.context_node_mask.shape[1]}"
            )
        if self.modality_mask.shape[1] != len(MODALITY_NAMES):
            raise ValueError(
                f"Expected modality mask width {len(MODALITY_NAMES)}, got {self.modality_mask.shape[1]}"
            )

        if limit is not None:
            n = int(limit)
            self.sequence_embedding = self.sequence_embedding[:n]
            self.structure_embedding = self.structure_embedding[:n]
            self.context_features = self.context_features[:n]
            self.context_node_features = self.context_node_features[:n]
            self.context_adjacency = self.context_adjacency[:n]
            self.context_node_mask = self.context_node_mask[:n]
            self.context_center_index = self.context_center_index[:n]
            self.modality_mask = self.modality_mask[:n]
            self.label_l1 = self.label_l1[:n]
            self.label_l2 = self.label_l2[:n]
            self.label_l3_core = self.label_l3_core[:n]
            self.sequence_length = self.sequence_length[:n]
            self.protein_id = self.protein_id[:n]
            self.embedding_id = self.embedding_id[:n]
            self.exact_sequence_rep_id = self.exact_sequence_rep_id[:n]
            self.homology_cluster_id = self.homology_cluster_id[:n]
            self.split = self.split[:n]
            self.split_strategy = self.split_strategy[:n]
            self.split_version = self.split_version[:n]
            self.status = self.status[:n]

    @classmethod
    def from_prepacked_dir(
        cls,
        prepacked_dir: str | Path,
        split: str,
        limit: int | None = None,
    ) -> "MultimodalCoreDataset":
        pack_path = Path(prepacked_dir) / f"multimodal_{split}.pt"
        return cls(pack_path, limit=limit)

    def __len__(self) -> int:
        return int(self.sequence_embedding.shape[0])

    def __getitem__(self, index: int) -> MultimodalBatch:
        ids = build_ids(
            protein_id=self.protein_id[index],
            embedding_id=self.embedding_id[index],
            exact_sequence_rep_id=self.exact_sequence_rep_id[index],
            context_key=self.protein_id[index],
        )
        labels = build_labels(
            int(self.label_l1[index].item()),
            int(self.label_l2[index].item()),
            int(self.label_l3_core[index].item()),
        )
        batch: MultimodalBatch = {
            "ids": ids,
            "labels": labels,
            "protein_id": self.protein_id[index],
            "embedding_id": self.embedding_id[index],
            "exact_sequence_rep_id": self.exact_sequence_rep_id[index],
            "context_key": self.protein_id[index],
            "label_l1": self.label_l1[index],
            "label_l2": self.label_l2[index],
            "label_l3_core": self.label_l3_core[index],
            "sequence_embedding": self.sequence_embedding[index],
            "structure_embedding": self.structure_embedding[index],
            "context_features": self.context_features[index],
            "context_node_features": self.context_node_features[index],
            "context_adjacency": self.context_adjacency[index],
            "context_node_mask": self.context_node_mask[index],
            "context_center_index": self.context_center_index[index],
            "modality_mask": self.modality_mask[index],
            "split": self.split[index],
            "split_strategy": self.split_strategy[index],
            "split_version": self.split_version[index],
            "homology_cluster_id": self.homology_cluster_id[index],
            "status": self.status[index],
            "context_mode": self.context_mode,
            "context_graph_version": self.context_graph_version,
            "sequence_length": self.sequence_length[index],
        }
        return batch

    def class_weights(self, field: str, num_classes: int) -> torch.Tensor:
        if field not in {"label_l1", "label_l2", "label_l3_core"}:
            raise KeyError(f"Unsupported label field for class weights: {field}")
        labels = getattr(self, field)
        counts = torch.bincount(labels, minlength=num_classes).float()
        total = counts.sum().item()
        weights = torch.zeros(num_classes, dtype=torch.float32)
        nonzero = counts > 0
        weights[nonzero] = total / (float(num_classes) * counts[nonzero])
        return weights

    def hierarchy_maps(
        self,
        num_l1: int | None = None,
        num_l2: int | None = None,
        num_l3: int | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        num_l3 = int(num_l3 if num_l3 is not None else (torch.max(self.label_l3_core).item() + 1))
        num_l2 = int(num_l2 if num_l2 is not None else (torch.max(self.label_l2).item() + 1))
        num_l1 = int(num_l1 if num_l1 is not None else (torch.max(self.label_l1).item() + 1))
        l3_to_l2 = torch.full((num_l3,), -1, dtype=torch.long)
        l2_to_l1 = torch.full((num_l2,), -1, dtype=torch.long)

        for i in range(len(self)):
            l3 = int(self.label_l3_core[i].item())
            l2 = int(self.label_l2[i].item())
            l1 = int(self.label_l1[i].item())

            if l3_to_l2[l3] not in (-1, l2):
                raise ValueError(f"Conflicting L3->L2 mapping for class {l3}")
            l3_to_l2[l3] = l2

            if l2_to_l1[l2] not in (-1, l1):
                raise ValueError(f"Conflicting L2->L1 mapping for class {l2}")
            l2_to_l1[l2] = l1

        if num_l1 <= 0:
            raise ValueError("num_l1 must be positive")
        return l3_to_l2, l2_to_l1

    def sampler_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "row_index": range(len(self)),
                "protein_id": self.protein_id,
                "embedding_id": self.embedding_id,
                "exact_sequence_rep_id": self.exact_sequence_rep_id,
                "homology_cluster_id": self.homology_cluster_id,
                "label_l3_core": self.label_l3_core.tolist(),
            }
        )


def build_pack_path(prepacked_dir: str | Path, split: str) -> Path:
    return Path(prepacked_dir) / f"multimodal_{split}.pt"
